import { workflow, node, trigger, expr, ifElse } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Gemini role input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
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
      campaign_id: expr("{{ $('Gemini role input').item.json.campaign_id }}"),
      prompt_key: expr("{{ $('Gemini role input').item.json.prompt_key }}"),
    }, matchingColumns: [], schema: [{ id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});
const primary = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Primary Gemini Flash Lite', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'YE5oyCWwpnQxVAi1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g1' }}"),
      parent_attempt_id: '',
      invocation_id: expr("{{ $('Gemini role input').item.json.base_invocation_id + '-g1' }}"),
      campaign_id: expr("{{ $('Gemini role input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Gemini role input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Gemini role input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Gemini role input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Gemini role input').item.json.agent_role }}"),
      prompt_key: expr("{{ $('Gemini role input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Load frozen role prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen role prompt').item.json.prompt.template + '\n\nCONTEXT:\n' + JSON.stringify($('Gemini role input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen role prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen role prompt').item.json.prompt.outputSchema_object) : $('Load frozen role prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ $('Gemini role input').item.json.model_waterfall[0].modelId }}"),
      reservation_usd: expr("{{ $('Gemini role input').item.json.reservation_usd }}"),
      input_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[0].inputCostPerMillionUsd }}"),
      output_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[0].outputCostPerMillionUsd }}"),
      repair_of_invocation_id: expr("{{ $('Gemini role input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});
const primaryUnavailable = ifElse({ version: 2.3, config: { name: 'Primary returned confirmed 503?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Primary Gemini Flash Lite').item.json.status || '' }}"), rightValue: 'unavailable_503', operator: { type: 'string', operation: 'notEquals' } },
  ],
} } } });
const fallbackOne = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Fallback Gemini 3 Flash', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'YE5oyCWwpnQxVAi1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g2' }}"),
      parent_attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g1' }}"),
      invocation_id: expr("{{ $('Gemini role input').item.json.base_invocation_id + '-g2' }}"),
      campaign_id: expr("{{ $('Gemini role input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Gemini role input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Gemini role input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Gemini role input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Gemini role input').item.json.agent_role }}"),
      prompt_key: expr("{{ $('Gemini role input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Load frozen role prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen role prompt').item.json.prompt.template + '\n\nCONTEXT:\n' + JSON.stringify($('Gemini role input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen role prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen role prompt').item.json.prompt.outputSchema_object) : $('Load frozen role prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ $('Gemini role input').item.json.model_waterfall[1].modelId }}"),
      reservation_usd: expr("{{ $('Gemini role input').item.json.reservation_usd }}"),
      input_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[1].inputCostPerMillionUsd }}"),
      output_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[1].outputCostPerMillionUsd }}"),
      repair_of_invocation_id: expr("{{ $('Gemini role input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});
const fallbackOneUnavailable = ifElse({ version: 2.3, config: { name: 'First fallback returned confirmed 503?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Fallback Gemini 3 Flash').item.json.status || '' }}"), rightValue: 'unavailable_503', operator: { type: 'string', operation: 'notEquals' } },
  ],
} } } });
const fallbackTwo = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Fallback Gemini 3.6 Flash', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'YE5oyCWwpnQxVAi1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g3' }}"),
      parent_attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g2' }}"),
      invocation_id: expr("{{ $('Gemini role input').item.json.base_invocation_id + '-g3' }}"),
      campaign_id: expr("{{ $('Gemini role input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Gemini role input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Gemini role input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Gemini role input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Gemini role input').item.json.agent_role }}"),
      prompt_key: expr("{{ $('Gemini role input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Load frozen role prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen role prompt').item.json.prompt.template + '\n\nCONTEXT:\n' + JSON.stringify($('Gemini role input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen role prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen role prompt').item.json.prompt.outputSchema_object) : $('Load frozen role prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ $('Gemini role input').item.json.model_waterfall[2].modelId }}"),
      reservation_usd: expr("{{ $('Gemini role input').item.json.reservation_usd }}"),
      input_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[2].inputCostPerMillionUsd }}"),
      output_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[2].outputCostPerMillionUsd }}"),
      repair_of_invocation_id: expr("{{ $('Gemini role input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});
const fallbackTwoUnavailable = ifElse({ version: 2.3, config: { name: 'Second fallback returned confirmed 503?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Fallback Gemini 3.6 Flash').item.json.status || '' }}"), rightValue: 'unavailable_503', operator: { type: 'string', operation: 'notEquals' } },
  ],
} } } });
const finalPrimary = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Final primary Gemini retry', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'YE5oyCWwpnQxVAi1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g4' }}"),
      parent_attempt_id: expr("{{ $('Gemini role input').item.json.base_attempt_id + '-g3' }}"),
      invocation_id: expr("{{ $('Gemini role input').item.json.base_invocation_id + '-g4' }}"),
      campaign_id: expr("{{ $('Gemini role input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Gemini role input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Gemini role input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Gemini role input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Gemini role input').item.json.agent_role }}"),
      prompt_key: expr("{{ $('Gemini role input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Load frozen role prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen role prompt').item.json.prompt.template + '\n\nCONTEXT:\n' + JSON.stringify($('Gemini role input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen role prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen role prompt').item.json.prompt.outputSchema_object) : $('Load frozen role prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ $('Gemini role input').item.json.model_waterfall[3].modelId }}"),
      reservation_usd: expr("{{ $('Gemini role input').item.json.reservation_usd }}"),
      input_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[3].inputCostPerMillionUsd }}"),
      output_cost_per_million_usd: expr("{{ $('Gemini role input').item.json.model_waterfall[3].outputCostPerMillionUsd }}"),
      repair_of_invocation_id: expr("{{ $('Gemini role input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});
const finalUnavailable = ifElse({ version: 2.3, config: { name: 'Final primary returned confirmed 503?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Final primary Gemini retry').item.json.status || '' }}"), rightValue: 'unavailable_503', operator: { type: 'string', operation: 'notEquals' } },
  ],
} } } });
const unresolved = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return operationally unresolved', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'operationally_unresolved', type: 'string' },
    { id: 'reason', name: 'reason', value: 'gemini_503_waterfall_exhausted', type: 'string' },
    { id: 'agent-role', name: 'agent_role', value: expr("{{ $('Gemini role input').item.json.agent_role }}"), type: 'string' },
  ] } } },
});
export default workflow('qb3-invoke-gemini-waterfall', 'Invoke Gemini agent with 503 waterfall')
  .add(input.to(loadPrompt).to(primary).to(primaryUnavailable.onFalse(
    fallbackOne.to(fallbackOneUnavailable.onFalse(
      fallbackTwo.to(fallbackTwoUnavailable.onFalse(
        finalPrimary.to(finalUnavailable.onFalse(unresolved))
      ))
    ))
  )));
