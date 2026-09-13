import { workflow, node, trigger, newCredential, expr, ifElse } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'attempt_id', type: 'string' }, { name: 'parent_attempt_id', type: 'string' },
    { name: 'invocation_id', type: 'string' }, { name: 'campaign_id', type: 'string' },
    { name: 'batch_id', type: 'string' }, { name: 'candidate_id', type: 'string' },
    { name: 'mission_id', type: 'string' }, { name: 'agent_role', type: 'string' },
    { name: 'prompt_key', type: 'string' }, { name: 'prompt_version', type: 'string' },
    { name: 'rendered_prompt', type: 'string' }, { name: 'output_schema', type: 'object' },
    { name: 'model_id', type: 'string' }, { name: 'reasoning_setting', type: 'string' },
    { name: 'reservation_usd', type: 'number' },
    { name: 'input_cost_per_million_usd', type: 'number' }, { name: 'output_cost_per_million_usd', type: 'number' },
  ] } } },
});

const reserve = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reserve this OpenAI attempt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O4Sfd0diGAB53tsL' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"), campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"), candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.parent_attempt_id || '' }}"), agent_role: expr("{{ $('Agent input').item.json.agent_role }}"),
      provider: 'openai', requested_model: expr("{{ $('Agent input').item.json.model_id }}"),
      reasoning_setting: expr("{{ $('Agent input').item.json.reasoning_setting }}"), reservation_usd: expr("{{ $('Agent input').item.json.reservation_usd }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'provider', displayName: 'provider', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'requested_model', displayName: 'requested_model', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reasoning_setting', displayName: 'reasoning_setting', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const reserved = ifElse({ version: 2.3, config: { name: 'Reservation succeeded?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.reserved }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ] },
} } });

const openai = node({
  type: '@n8n/n8n-nodes-langchain.openAi', version: 2.3,
  config: { name: 'OpenAI role agent — paid', onError: 'continueRegularOutput', credentials: { openAiApi: newCredential('Question Bank v3 OpenAI') }, parameters: {
    resource: 'text', operation: 'response', modelId: { __rl: true, mode: 'id', value: expr("{{ $('Agent input').item.json.model_id }}") },
    responses: { values: [{ type: 'text', role: 'user', content: expr("{{ $('Agent input').item.json.rendered_prompt }}") }] },
    simplify: false, builtInTools: {}, store: false,
    options: {
      maxTokens: 4096, serviceTier: 'default', parallelToolCalls: false, maxToolCalls: 0, maxToolsIterations: 1,
      reasoning: { reasoningOptions: { effort: expr("{{ $('Agent input').item.json.reasoning_setting }}"), summary: 'none' } },
      textFormat: { textOptions: { type: 'json_schema', name: 'question_bank_agent_output', schema: expr("{{ $('Agent input').item.json.output_schema }}"), strict: true, verbosity: 'low' } },
    },
  } },
});

const succeeded = ifElse({ version: 2.3, config: { name: 'OpenAI returned output?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($json.output?.length || $json.output_text?.length || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const hasStatus = ifElse({ version: 2.3, config: { name: 'Provider returned HTTP status?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($json.statusCode || $json.httpCode || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const reconcile = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reconcile OpenAI usage', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O2721VLonNSui2TW' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      actual_cost_usd: expr("{{ ((($('OpenAI role agent — paid').item.json.usage?.input_tokens || 0) * $('Agent input').item.json.input_cost_per_million_usd) + (($('OpenAI role agent — paid').item.json.usage?.output_tokens || 0) * $('Agent input').item.json.output_cost_per_million_usd)) / 1000000 }}"),
      reported_model: expr("{{ $('OpenAI role agent — paid').item.json.model || $('Agent input').item.json.model_id }}"),
      usage: expr("{{ $('OpenAI role agent — paid').item.json.usage || {} }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'actual_cost_usd', displayName: 'actual_cost_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reported_model', displayName: 'reported_model', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'usage', displayName: 'usage', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const persist = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist prompt and output', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 't7YcO0u9cCMxETbS' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"), attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"), mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Agent input').item.json.agent_role }}"), prompt_key: expr("{{ $('Agent input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Agent input').item.json.prompt_version }}"), rendered_prompt: expr("{{ $('Agent input').item.json.rendered_prompt }}"),
      raw_response: expr("{{ JSON.stringify($('OpenAI role agent — paid').item.json) }}"),
      structured_response: expr("{{ (() => { const r = $('OpenAI role agent — paid').item.json; const t = r.output_text || r.output?.flatMap(o => o.content || []).find(c => c.type === 'output_text')?.text || '{}'; return typeof t === 'string' ? JSON.parse(t) : t; })() }}"),
      status: 'succeeded', repair_of_invocation_id: '',
    }, matchingColumns: [], schema: [
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'raw_response', displayName: 'raw_response', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'structured_response', displayName: 'structured_response', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'status', displayName: 'status', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const release = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Release confirmed failure reservation', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'z0kaN1S9ci6Ekn1R' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'openai_http_error', status_code: $('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode, message: $('OpenAI role agent — paid').item.json.error?.message || $('OpenAI role agent — paid').item.json.message || 'OpenAI request failed' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const retrySignal = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return explicit retry signal', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'retryable_failure', type: 'string' },
    { id: 'attempt-id', name: 'attempt_id', value: expr("{{ $('Agent input').item.json.attempt_id }}"), type: 'string' },
  ] } } },
});

const unknown = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Record ambiguous OpenAI spend', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'DsoqFjpqv1mhOQU8' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'openai_ambiguous_transport', message: $('OpenAI role agent — paid').item.json.error?.message || $('OpenAI role agent — paid').item.json.message || 'OpenAI result unknown' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

export default workflow('qb3-invoke-openai-attempt', 'Invoke OpenAI agent attempt')
  .add(input).to(reserve).to(reserved.onTrue(
    openai.to(succeeded
      .onTrue(reconcile.to(persist))
      .onFalse(hasStatus.onTrue(release.to(retrySignal)).onFalse(unknown)))
  ));
