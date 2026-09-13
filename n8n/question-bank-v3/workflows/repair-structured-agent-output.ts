import { workflow, node, trigger, expr, switchCase } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' }, { name: 'mission_id', type: 'string' },
    { name: 'attempt_id', type: 'string' }, { name: 'invocation_id', type: 'string' },
    { name: 'context', type: 'object' },
    { name: 'provider_family', type: 'string' },
    { name: 'repair_of_invocation_id', type: 'string' },
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), prompt_key: 'repair_structured_output',
    }, matchingColumns: [], schema: [{ id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true }
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
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      base_attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      base_invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      context: expr("{{ $('Agent input').item.json.context }}"),
      model_waterfall: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini'); return typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; })() }}"),
      reasoning_setting: 'low',
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini').reservationUsd }}"),
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'base_attempt_id', displayName: 'base_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'base_invocation_id', displayName: 'base_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'context', displayName: 'context', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_waterfall', displayName: 'model_waterfall', type: 'array', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reasoning_setting', displayName: 'reasoning_setting', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }
  } },
});

const openai = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair output — OpenAI low', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2qbdNZNjME7n1pKJ' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      base_attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      base_invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      context: expr("{{ $('Agent input').item.json.context }}"),
      model_waterfall: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai'); return typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; })() }}"),
      reasoning_setting: 'low',
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai').reservationUsd }}"),
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'base_attempt_id', displayName: 'base_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'base_invocation_id', displayName: 'base_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'context', displayName: 'context', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_waterfall', displayName: 'model_waterfall', type: 'array', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reasoning_setting', displayName: 'reasoning_setting', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }
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
