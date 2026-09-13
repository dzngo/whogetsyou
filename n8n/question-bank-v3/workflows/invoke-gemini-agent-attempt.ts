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
    { name: 'model_id', type: 'string' }, { name: 'reservation_usd', type: 'number' },
    { name: 'input_cost_per_million_usd', type: 'number' }, { name: 'output_cost_per_million_usd', type: 'number' },
  ] } } },
});

const reserve = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reserve this Gemini attempt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O4Sfd0diGAB53tsL' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"), campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"), candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.parent_attempt_id || '' }}"), agent_role: expr("{{ $('Agent input').item.json.agent_role }}"),
      provider: 'gemini', requested_model: expr("{{ $('Agent input').item.json.model_id }}"), reasoning_setting: 'high_dynamic',
      reservation_usd: expr("{{ $('Agent input').item.json.reservation_usd }}"),
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

const gemini = node({
  type: '@n8n/n8n-nodes-langchain.googleGemini', version: 1.1,
  config: { name: 'Gemini role agent — paid', onError: 'continueRegularOutput', credentials: { googlePalmApi: newCredential('Question Bank v3 Gemini') }, parameters: {
    resource: 'text', operation: 'message', modelId: { __rl: true, mode: 'id', value: expr("{{ $('Agent input').item.json.model_id }}") },
    messages: { values: [{ role: 'user', content: expr("{{ $('Agent input').item.json.rendered_prompt + '\n\nReturn only JSON matching this schema:\n' + JSON.stringify($('Agent input').item.json.output_schema) }}") }] },
    simplify: false, jsonOutput: true,
    builtInTools: { googleSearch: false, urlContext: false, codeExecution: false },
    options: { thinkingBudget: -1, maxOutputTokens: 4096, temperature: 1.1, includeMergedResponse: true },
  } },
});

const succeeded = ifElse({ version: 2.3, config: { name: 'Gemini returned content?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($json.candidates?.[0]?.content?.parts?.length || $json.text?.length || $json.response?.length || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const is503 = ifElse({ version: 2.3, config: { name: 'Confirmed 503 UNAVAILABLE?', parameters: {
  conditions: { options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' }, combinator: 'or', conditions: [
    { leftValue: expr("{{ String($json.statusCode || $json.httpCode || '') }}"), rightValue: '503', operator: { type: 'string', operation: 'equals' } },
    { leftValue: expr("{{ String($json.error?.message || $json.message || '') }}"), rightValue: 'UNAVAILABLE', operator: { type: 'string', operation: 'contains' } },
  ] },
} } });

const reconcile = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reconcile Gemini usage', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O2721VLonNSui2TW' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      actual_cost_usd: expr("{{ ((($('Gemini role agent — paid').item.json.usageMetadata?.promptTokenCount || 0) * $('Agent input').item.json.input_cost_per_million_usd) + ((($('Gemini role agent — paid').item.json.usageMetadata?.candidatesTokenCount || 0) + ($('Gemini role agent — paid').item.json.usageMetadata?.thoughtsTokenCount || 0)) * $('Agent input').item.json.output_cost_per_million_usd)) / 1000000 }}"),
      reported_model: expr("{{ $('Gemini role agent — paid').item.json.modelVersion || $('Agent input').item.json.model_id }}"),
      usage: expr("{{ $('Gemini role agent — paid').item.json.usageMetadata || {} }}"),
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
      raw_response: expr("{{ JSON.stringify($('Gemini role agent — paid').item.json) }}"),
      structured_response: expr("{{ (() => { const r = $('Gemini role agent — paid').item.json; const t = r.mergedResponse || r.text || r.response || r.candidates?.[0]?.content?.parts?.map(p => p.text || '').join('') || '{}'; return typeof t === 'string' ? JSON.parse(t.replace(/^```json\\s*|```$/g, '').trim()) : t; })() }}"),
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

const release503 = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Release confirmed 503 reservation', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'z0kaN1S9ci6Ekn1R' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'gemini_503_unavailable', message: $('Gemini role agent — paid').item.json.error?.message || $('Gemini role agent — paid').item.json.message || '503 UNAVAILABLE' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const retrySignal = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return explicit 503 retry signal', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'unavailable_503', type: 'string' },
    { id: 'attempt-id', name: 'attempt_id', value: expr("{{ $('Agent input').item.json.attempt_id }}"), type: 'string' },
    { id: 'model-id', name: 'model_id', value: expr("{{ $('Agent input').item.json.model_id }}"), type: 'string' },
  ] } } },
});

const unknown = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Record ambiguous Gemini spend', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'DsoqFjpqv1mhOQU8' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'gemini_provider_failure', message: $('Gemini role agent — paid').item.json.error?.message || $('Gemini role agent — paid').item.json.message || 'Gemini result unknown' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

export default workflow('qb3-invoke-gemini-attempt', 'Invoke Gemini agent attempt')
  .add(input).to(reserve).to(reserved.onTrue(
    gemini.to(succeeded
      .onTrue(reconcile.to(persist))
      .onFalse(is503.onTrue(release503.to(retrySignal)).onFalse(unknown)))
  ));
