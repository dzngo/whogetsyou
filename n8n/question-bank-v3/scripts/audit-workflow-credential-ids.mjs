#!/usr/bin/env node

import { readFile, readdir } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const resources = JSON.parse(await readFile(join(root, 'n8n-resources.json'), 'utf8'));
const allowed = new Set(
  Object.values(resources.credentials).map(({ name, id }) => `${name}\u0000${id}`),
);
const files = (await readdir(join(root, 'workflows')))
  .filter((name) => name.endsWith('.ts'))
  .sort();
const pattern = /newCredential\('([^']+)', '([^']+)'\)/g;

const actualByFile = {};
for (const file of files) {
  const source = await readFile(join(root, 'workflows', file), 'utf8');
  actualByFile[file] = [];
  for (const match of source.matchAll(pattern)) {
    const key = `${match[1]}\u0000${match[2]}`;
    if (!allowed.has(key)) {
      throw new Error(`${file}: unexpected credential binding ${match[1]} (${match[2]})`);
    }
    const nodeNames = [...source.slice(0, match.index).matchAll(/config:\s*\{\s*name:\s*'([^']+)'/g)];
    const nodeName = nodeNames.at(-1)?.[1];
    if (!nodeName) throw new Error(`${file}: could not resolve node owning credential binding`);
    actualByFile[file].push(`${nodeName} :: ${key.replace('\u0000', ' / ')}`);
  }
  actualByFile[file].sort();
  if (actualByFile[file].length === 0) delete actualByFile[file];
}

const pg = 'Question Bank v3 Postgres / h3ZyIgobxf9KpDG3';
const expectedByFile = {
  'apply-admission-decision.ts': [`Apply decision transaction :: ${pg}`],
  'apply-question-metadata.ts': [`Apply metadata transaction :: ${pg}`],
  'assign-question-bank-batch-metadata.ts': [`Apply themes and metadata :: ${pg}`, `Read newly accepted questions and themes :: ${pg}`].sort(),
  'build-distribution-snapshot.ts': [`Build frozen snapshot :: ${pg}`],
  'complete-question-bank-batch.ts': [`Complete batch and refresh evidence :: ${pg}`],
  'continue-question-bank-campaign.ts': [`Create bounded internal batch tokens :: ${pg}`, `Register campaign execution context :: ${pg}`, `Return durable campaign status :: ${pg}`].sort(),
  'control-question-bank-campaign.ts': [`Apply campaign command :: ${pg}`, 'Campaign control form :: Question Bank v3 Operator Basic Auth / RhDqaHYrJyNybEEm'].sort(),
  'embed-and-retrieve-neighbours.ts': [`Persist embedding invocation trace :: ${pg}`, `Store vector and retrieve top 10 :: ${pg}`, 'OpenAI embedding — paid :: Question Bank v3 OpenAI HTTP / znA69osGbjXZQJsa'].sort(),
  'evaluate-question-bank-batch-quality.ts': [`Apply escalation decisions :: ${pg}`, `Apply independent quality decisions :: ${pg}`, `Isolate failed escalation group :: ${pg}`, `Isolate failed quality group :: ${pg}`, `Read quality groups of ten :: ${pg}`, `Read uncertain quality groups :: ${pg}`].sort(),
  'export-question-bank.ts': [`Select authoritative rows :: ${pg}`, 'Export filters :: Question Bank v3 Operator Basic Auth / RhDqaHYrJyNybEEm'].sort(),
  'generate-question-bank-batch.ts': [`Return persisted candidate count :: ${pg}`],
  'handle-question-bank-workflow-errors.ts': [`Persist sanitized failure :: ${pg}`],
  'initialize-question-bank-campaign.ts': [`Create campaign with immutable configuration :: ${pg}`],
  'invoke-gemini-agent-attempt.ts': [`Persist failed Gemini invocation :: ${pg}`, 'Gemini role agent — paid :: Question Bank v3 Gemini / saq0VdVjhktN52p7'].sort(),
  'invoke-openai-agent-attempt.ts': [`Persist failed OpenAI invocation :: ${pg}`, 'OpenAI role agent — paid :: Question Bank v3 OpenAI / EtyHRCKzh3b0xyy0'].sort(),
  'judge-and-admit-question-bank-batch.ts': [`Apply semantic decisions and admit distinct :: ${pg}`, `Create semantic work tokens :: ${pg}`, `Isolate failed semantic group :: ${pg}`, `Read next candidate with fresh neighbours :: ${pg}`].sort(),
  'load-frozen-prompt-snapshot.ts': [`Load immutable prompt :: ${pg}`],
  'normalize-and-preflight-question.ts': [`Normalize and check exact duplicate :: ${pg}`],
  'persist-agent-run.ts': [`Persist complete trace :: ${pg}`],
  'persist-mission-and-candidates.ts': [`Persist mission and optional candidates :: ${pg}`],
  'preflight-and-embed-question-bank-batch.ts': [`Isolate failed embedding candidate :: ${pg}`, `Read quality-approved candidates :: ${pg}`].sort(),
  'process-one-question-bank-batch.ts': [`Begin or resume one durable batch :: ${pg}`, `Read immutable batch context :: ${pg}`].sort(),
  'read-and-update-campaign-state.ts': [`Read or update campaign :: ${pg}`],
  'reconcile-provider-attempt.ts': [`Reconcile in PostgreSQL :: ${pg}`],
  'record-unknown-provider-spend.ts': [`Mark unknown in PostgreSQL :: ${pg}`],
  'release-provider-attempt.ts': [`Release in PostgreSQL :: ${pg}`],
  'reserve-provider-budget.ts': [`Reserve in PostgreSQL :: ${pg}`],
  'run-question-bank-campaign.ts': ['Launch campaign form :: Question Bank v3 Operator Basic Auth / RhDqaHYrJyNybEEm'],
};

if (JSON.stringify(actualByFile) !== JSON.stringify(expectedByFile)) {
  throw new Error(`per-workflow credential bindings changed:\nactual=${JSON.stringify(actualByFile, null, 2)}\nexpected=${JSON.stringify(expectedByFile, null, 2)}`);
}

console.log(`Credential audit passed: ${Object.values(actualByFile).flat().length} exact per-node bindings across ${files.length} workflow sources.`);
