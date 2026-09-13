import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outputDir = resolve(here, '..', 'workflows');
mkdirSync(outputDir, { recursive: true });

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

function renderRepair() {
  const geminiInputs = providerInputs('gemini', 'structured_output_repair', 'repair_structured_output', 'low');
  const openaiInputs = providerInputs('openai', 'structured_output_repair', 'repair_structured_output', 'low');
  return `import { workflow, node, trigger, expr, switchCase } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [${commonInputs}
    { name: 'provider_family', type: 'string' },
    { name: 'repair_of_invocation_id', type: 'string' },
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    ${loadInputs.replace('PROMPT_KEY', "'repair_structured_output'")}
  } },
});

const route = switchCase({ version: 3.4, config: { name: 'Use original provider family', parameters: {
  mode: 'rules', rules: { values: [
    { outputKey: 'gemini', conditions: { options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: expr("{{ $('Agent input').item.json.provider_family }}"), rightValue: 'gemini', operator: { type: 'string', operation: 'equals' } }] } },
    { outputKey: 'openai', conditions: { options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: expr("{{ $('Agent input').item.json.provider_family }}"), rightValue: 'openai', operator: { type: 'string', operation: 'equals' } }] } },
  ] }, options: { fallbackOutput: 'none' },
} } });

const gemini = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair output — Gemini low', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'tiKFH1SLj7mH4dc9' },
    ${geminiInputs}
  } },
});

const openai = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair output — OpenAI low', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2qbdNZNjME7n1pKJ' },
    ${openaiInputs}
  } },
});

const returnGeminiRepair = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return Gemini repair result', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: expr("{{ $('Repair output — Gemini low').item.json.structured_response?.repairable === true ? 'succeeded' : 'operationally_unresolved' }}"), type: 'string' },
    { id: 'structured-response', name: 'structured_response', value: expr("{{ $('Repair output — Gemini low').item.json.structured_response?.repaired_output || {} }}"), type: 'object' },
    { id: 'invocation-id', name: 'invocation_id', value: expr("{{ $('Repair output — Gemini low').item.json.invocation_id || '' }}"), type: 'string' },
    { id: 'reason', name: 'reason', value: expr("{{ $('Repair output — Gemini low').item.json.structured_response?.error || '' }}"), type: 'string' },
  ] } } },
});

const returnOpenAIRepair = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return OpenAI repair result', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: expr("{{ $('Repair output — OpenAI low').item.json.structured_response?.repairable === true ? 'succeeded' : 'operationally_unresolved' }}"), type: 'string' },
    { id: 'structured-response', name: 'structured_response', value: expr("{{ $('Repair output — OpenAI low').item.json.structured_response?.repaired_output || {} }}"), type: 'object' },
    { id: 'invocation-id', name: 'invocation_id', value: expr("{{ $('Repair output — OpenAI low').item.json.invocation_id || '' }}"), type: 'string' },
    { id: 'reason', name: 'reason', value: expr("{{ $('Repair output — OpenAI low').item.json.structured_response?.error || '' }}"), type: 'string' },
  ] } } },
});

export default workflow('qb3-repair-structured-output', 'Repair structured agent output')
  .add(input).to(loadPrompt).to(route
    .onCase(0, gemini.to(returnGeminiRepair))
    .onCase(1, openai.to(returnOpenAIRepair))
  );
`;
}

for (const role of roles) {
  writeFileSync(resolve(outputDir, `${role[0]}.ts`), renderRole(role));
}

writeFileSync(resolve(outputDir, 'repair-structured-agent-output.ts'), renderRepair());
