import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outputDir = resolve(here, '..', 'workflows');

const field = (id, type) => `{ id: '${id}', displayName: '${id}', type: '${type}', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }`;
const attemptFields = [
  ['attempt_id', 'string'], ['parent_attempt_id', 'string'], ['invocation_id', 'string'],
  ['campaign_id', 'string'], ['batch_id', 'string'], ['candidate_id', 'string'],
  ['mission_id', 'string'], ['agent_role', 'string'], ['prompt_key', 'string'],
  ['prompt_version', 'string'], ['rendered_prompt', 'string'], ['output_schema', 'object'],
  ['model_id', 'string'], ['reasoning_setting', 'string'], ['reservation_usd', 'number'],
  ['input_cost_per_million_usd', 'number'], ['output_cost_per_million_usd', 'number'],
  ['repair_of_invocation_id', 'string'],
];

const commonHeader = (provider) => `import { workflow, node, trigger, expr, ifElse } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: '${provider} role input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' }, { name: 'mission_id', type: 'string' },
    { name: 'base_attempt_id', type: 'string' }, { name: 'base_invocation_id', type: 'string' },
    { name: 'agent_role', type: 'string' }, { name: 'prompt_key', type: 'string' },
    { name: 'context', type: 'object' }, { name: 'model_waterfall', type: 'array' },
    { name: 'reasoning_setting', type: 'string' }, { name: 'reservation_usd', type: 'number' },
    { name: 'repair_of_invocation_id', type: 'string' },
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen role prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('${provider} role input').item.json.campaign_id }}"),
      prompt_key: expr("{{ $('${provider} role input').item.json.prompt_key }}"),
    }, matchingColumns: [], schema: [${field('campaign_id', 'string')}, ${field('prompt_key', 'string')}], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});
`;

const attemptNode = ({ provider, variable, name, number, modelIndex = 0 }) => {
  const prefix = provider === 'Gemini' ? 'g' : 'o';
  const runtimeId = provider === 'Gemini' ? 'YE5oyCWwpnQxVAi1' : 'p6V8CLoucC9GvQCd';
  const parent = number === 1 ? "''" : `expr("{{ $('${provider} role input').item.json.base_attempt_id + '-${prefix}${number - 1}' }}")`;
  const reasoningLine = provider === 'OpenAI'
    ? `      reasoning_setting: expr("{{ $('OpenAI role input').item.json.reasoning_setting }}"),\n`
    : '';
  return `const ${variable} = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '${name}', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '${runtimeId}' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('${provider} role input').item.json.base_attempt_id + '-${prefix}${number}' }}"),
      parent_attempt_id: ${parent},
      invocation_id: expr("{{ $('${provider} role input').item.json.base_invocation_id + '-${prefix}${number}' }}"),
      campaign_id: expr("{{ $('${provider} role input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('${provider} role input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('${provider} role input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('${provider} role input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('${provider} role input').item.json.agent_role }}"),
      prompt_key: expr("{{ $('${provider} role input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Load frozen role prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen role prompt').item.json.prompt.template + '\\n\\nCONTEXT:\\n' + JSON.stringify($('${provider} role input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen role prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen role prompt').item.json.prompt.outputSchema_object) : $('Load frozen role prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ $('${provider} role input').item.json.model_waterfall[${modelIndex}].modelId }}"),
${reasoningLine}      reservation_usd: expr("{{ $('${provider} role input').item.json.reservation_usd }}"),
      input_cost_per_million_usd: expr("{{ $('${provider} role input').item.json.model_waterfall[${modelIndex}].inputCostPerMillionUsd }}"),
      output_cost_per_million_usd: expr("{{ $('${provider} role input').item.json.model_waterfall[${modelIndex}].outputCostPerMillionUsd }}"),
      repair_of_invocation_id: expr("{{ $('${provider} role input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      ${attemptFields.filter(([id]) => provider === 'OpenAI' || id !== 'reasoning_setting').map(([id, type]) => field(id, type)).join(',\n      ')}
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});
`;
};

const conditionNode = (variable, name, expected, sourceNode) => `const ${variable} = ifElse({ version: 2.3, config: { name: '${name}', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('${sourceNode}').item.json.status || '' }}"), rightValue: '${expected}', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });
`;

const unresolvedNode = (provider, reason) => `const unresolved = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return operationally unresolved', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'operationally_unresolved', type: 'string' },
    { id: 'reason', name: 'reason', value: '${reason}', type: 'string' },
    { id: 'agent-role', name: 'agent_role', value: expr("{{ $('${provider} role input').item.json.agent_role }}"), type: 'string' },
  ] } } },
});
`;

const gemini = commonHeader('Gemini')
  + attemptNode({ provider: 'Gemini', variable: 'primary', name: 'Primary Gemini Flash Lite', number: 1, modelIndex: 0 })
  + conditionNode('primaryUnavailable', 'Primary returned confirmed 503?', 'unavailable_503', 'Primary Gemini Flash Lite')
  + attemptNode({ provider: 'Gemini', variable: 'fallbackOne', name: 'Fallback Gemini 3 Flash', number: 2, modelIndex: 1 })
  + conditionNode('fallbackOneUnavailable', 'First fallback returned confirmed 503?', 'unavailable_503', 'Fallback Gemini 3 Flash')
  + attemptNode({ provider: 'Gemini', variable: 'fallbackTwo', name: 'Fallback Gemini 3.6 Flash', number: 3, modelIndex: 2 })
  + conditionNode('fallbackTwoUnavailable', 'Second fallback returned confirmed 503?', 'unavailable_503', 'Fallback Gemini 3.6 Flash')
  + attemptNode({ provider: 'Gemini', variable: 'finalPrimary', name: 'Final primary Gemini retry', number: 4, modelIndex: 3 })
  + conditionNode('finalUnavailable', 'Final primary returned confirmed 503?', 'unavailable_503', 'Final primary Gemini retry')
  + unresolvedNode('Gemini', 'gemini_503_waterfall_exhausted')
  + `export default workflow('qb3-invoke-gemini-waterfall', 'Invoke Gemini agent with 503 waterfall')
  .add(input.to(loadPrompt).to(primary).to(primaryUnavailable.onTrue(
    fallbackOne.to(fallbackOneUnavailable.onTrue(
      fallbackTwo.to(fallbackTwoUnavailable.onTrue(
        finalPrimary.to(finalUnavailable.onTrue(unresolved))
      ))
    ))
  )));
`;

const openai = commonHeader('OpenAI')
  + attemptNode({ provider: 'OpenAI', variable: 'primary', name: 'Primary OpenAI attempt', number: 1 })
  + conditionNode('primaryFailed', 'Primary returned a definite retryable failure?', 'retryable_failure', 'Primary OpenAI attempt')
  + attemptNode({ provider: 'OpenAI', variable: 'retry', name: 'Explicit same-model OpenAI retry', number: 2 })
  + conditionNode('retryFailed', 'Retry failed definitely?', 'retryable_failure', 'Explicit same-model OpenAI retry')
  + unresolvedNode('OpenAI', 'openai_retry_exhausted')
  + `export default workflow('qb3-invoke-openai-retry', 'Invoke OpenAI agent with explicit retry')
  .add(input.to(loadPrompt).to(primary).to(primaryFailed.onTrue(retry.to(retryFailed.onTrue(unresolved)))));
`;

writeFileSync(resolve(outputDir, 'invoke-gemini-agent-with-waterfall.ts'), gemini);
writeFileSync(resolve(outputDir, 'invoke-openai-agent-with-retry.ts'), openai);
