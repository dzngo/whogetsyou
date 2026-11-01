import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' }, { name: 'mission_id', type: 'string' },
    { name: 'attempt_id', type: 'string' }, { name: 'invocation_id', type: 'string' },
    { name: 'context', type: 'object' }, { name: 'work_group_id', type: 'string' },
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), prompt_key: 'evaluate_quality',
    }, matchingColumns: [], schema: [{ id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true }
  } },
});

const invoke = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Evaluate question quality — OpenAI medium', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2qbdNZNjME7n1pKJ' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      base_attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      base_invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      agent_role: 'quality_judge', prompt_key: 'evaluate_quality',
      context: expr("{{ $('Agent input').item.json.context }}"),
      model_waterfall: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'quality_judge'); return typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; })() }}"),
      reasoning_setting: 'medium',
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'quality_judge').reservationUsd }}"),
      work_group_id: expr("{{ $('Agent input').item.json.work_group_id || '' }}"),
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
      { id: 'work_group_id', displayName: 'work_group_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }
  } },
});

export default workflow('qb3-evaluate-question-quality', 'Evaluate question quality').add(input.to(loadPrompt).to(invoke));
