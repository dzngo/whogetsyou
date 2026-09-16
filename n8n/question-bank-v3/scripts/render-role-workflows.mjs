import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outputDir = resolve(here, '..', 'workflows');
mkdirSync(outputDir, { recursive: true });
const checkOnly = process.argv.includes('--check');

function writeOrCheck(path, content) {
  if (checkOnly) {
    const existing = readFileSync(path, 'utf8');
    if (existing !== content) {
      throw new Error(`Generated workflow is stale: ${path}`);
    }
    return;
  }
  writeFileSync(path, content);
}

const roles = [
  ['observe-question-bank-diversity', 'Observe Question Bank diversity', 'observation', 'observe_diversity', 'gemini', 'high'],
  ['write-generation-missions', 'Write generation missions', 'mission_writer', 'write_generation_missions', 'gemini', 'high'],
  ['generate-questions', 'Generate questions', 'creative', 'generate_questions', 'gemini', 'high'],
  ['evaluate-question-quality', 'Evaluate question quality', 'quality_judge', 'evaluate_quality', 'openai', 'medium'],
  ['escalate-uncertain-quality-decisions', 'Escalate uncertain quality decisions', 'quality_escalation', 'escalate_quality', 'openai', 'high'],
  ['judge-semantic-duplication', 'Judge semantic duplication', 'semantic_judge', 'judge_semantic_duplication', 'openai', 'high'],
  ['assign-themes-and-metadata', 'Assign themes and metadata', 'theme_metadata', 'assign_themes_metadata', 'openai', 'medium'],
];

const commonInputs = `
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' }, { name: 'mission_id', type: 'string' },
    { name: 'attempt_id', type: 'string' }, { name: 'invocation_id', type: 'string' },
    { name: 'context', type: 'object' },`;

const field = (id, type) => `{ id: '${id}', displayName: '${id}', type: '${type}', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }`;

const loadInputs = `workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), prompt_key: PROMPT_KEY,
    }, matchingColumns: [], schema: [${field('campaign_id', 'string')}, ${field('prompt_key', 'string')}], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true }`;

function providerInputs(provider, role, promptKey, reasoning) {
  const runtimeKey = role === 'structured_output_repair'
    ? `structured_output_repair_${provider}`
    : role;
  const repairValue = role === 'structured_output_repair'
    ? `\n      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),`
    : '';
  const values = `
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      base_attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      base_invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      agent_role: '${role}', prompt_key: '${promptKey}',
      context: expr("{{ $('Agent input').item.json.context }}"),
      model_waterfall: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === '${runtimeKey}'); return typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; })() }}"),
      reasoning_setting: '${reasoning}',
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === '${runtimeKey}').reservationUsd }}"),${repairValue}`;
  const fields = [
    ['campaign_id','string'], ['batch_id','string'], ['candidate_id','string'],
    ['mission_id','string'], ['base_attempt_id','string'], ['base_invocation_id','string'],
    ['agent_role','string'], ['prompt_key','string'], ['context','object'],
    ['model_waterfall','array'], ['reasoning_setting','string'], ['reservation_usd','number'],
    ...(role === 'structured_output_repair' ? [['repair_of_invocation_id','string']] : []),
  ].map(([id,type]) => field(id,type)).join(',\n      ');
  return `workflowInputs: { mappingMode: 'defineBelow', value: {${values}\n    }, matchingColumns: [], schema: [\n      ${fields}\n    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }`;
}

function renderRole([slug, name, role, promptKey, provider, reasoning]) {
  const runtimeId = provider === 'gemini' ? 'tiKFH1SLj7mH4dc9' : '2qbdNZNjME7n1pKJ';
  return `import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [${commonInputs}
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    ${loadInputs.replace('PROMPT_KEY', `'${promptKey}'`)}
  } },
});

const invoke = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '${name} — ${provider === 'gemini' ? 'Gemini high thinking' : `OpenAI ${reasoning}`}', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '${runtimeId}' },
    ${providerInputs(provider, role, promptKey, reasoning)}
  } },
});

export default workflow('qb3-${slug}', '${name}').add(input).to(loadPrompt).to(invoke);
`;
}

for (const role of roles) {
  writeOrCheck(resolve(outputDir, `${role[0]}.ts`), renderRole(role));
}
