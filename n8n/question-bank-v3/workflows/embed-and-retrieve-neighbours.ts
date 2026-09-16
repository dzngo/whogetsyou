import { workflow, node, trigger, newCredential, expr, ifElse, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'attempt_id', type: 'string' },
    { name: 'campaign_id', type: 'string' },
    { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' },
    { name: 'question_text', type: 'string' },
    { name: 'reservation_usd', type: 'number' },
    { name: 'input_cost_per_million_usd', type: 'number' },
  ] } } },
});

const reserve = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reserve embedding budget', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O4Sfd0diGAB53tsL' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Input').item.json.attempt_id }}"), campaign_id: expr("{{ $('Input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Input').item.json.batch_id || '' }}"), candidate_id: expr("{{ $('Input').item.json.candidate_id }}"),
      parent_attempt_id: '', agent_role: 'embedding', provider: 'openai', requested_model: 'text-embedding-3-small',
      reasoning_setting: 'none', reservation_usd: expr("{{ $('Input').item.json.reservation_usd }}"),
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
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const reserved = ifElse({ version: 2.3, config: { name: 'Reservation succeeded?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Reserve embedding budget').item.json.reserved }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ] },
} } });

const existingResult = ifElse({ version: 2.3, config: { name: 'Existing traced embedding?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Reserve embedding budget').item.json.status || '' }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const returnCached = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return cached embedding result', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'cached-status', name: 'status', type: 'string', value: expr("{{ $('Reserve embedding budget').item.json.structured_response?.transport_status || $('Reserve embedding budget').item.json.structured_response?.status || $('Reserve embedding budget').item.json.status }}") },
    { id: 'cached-candidate', name: 'candidate_id', type: 'string', value: expr("{{ $('Reserve embedding budget').item.json.structured_response?.candidate_id || $('Reserve embedding budget').item.json.candidate_id || $('Input').item.json.candidate_id }}") },
    { id: 'cached-neighbours', name: 'neighbours', type: 'array', value: expr("{{ $('Reserve embedding budget').item.json.structured_response?.neighbours || $('Reserve embedding budget').item.json.neighbours || null }}") },
  ] } } },
});

const stopDuplicateWorker = node({
  type: 'n8n-nodes-base.filter', version: 2.3,
  config: { name: 'Stop duplicate worker while lease is active', parameters: { conditions: {
    options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 }, combinator: 'and', conditions: [
      { leftValue: expr("{{ $('Return cached embedding result').item.json.status || '' }}"), rightValue: 'in_flight', operator: { type: 'string', operation: 'notEquals' } },
    ],
  } } },
});

const returnUnavailable = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return embedding reservation failure', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'unavailable-status', name: 'status', value: 'failed', type: 'string' },
    { id: 'unavailable-reason', name: 'reason', value: expr("{{ $('Reserve embedding budget').item.json.reason || 'embedding_budget_unavailable' }}"), type: 'string' },
    { id: 'unavailable-candidate', name: 'candidate_id', value: expr("{{ $('Input').item.json.candidate_id }}"), type: 'string' },
  ] } } },
});

const embed = node({
  type: 'n8n-nodes-base.httpRequest', version: 4.4,
  config: { name: 'OpenAI embedding — paid', onError: 'continueRegularOutput', credentials: {
    httpTemplatedCustomAuth: newCredential('Question Bank v3 OpenAI HTTP', 'znA69osGbjXZQJsa'),
  }, parameters: {
    method: 'POST', url: 'https://api.openai.com/v1/embeddings',
    authentication: 'genericCredentialType', genericAuthType: 'httpTemplatedCustomAuth',
    sendBody: true, contentType: 'json', specifyBody: 'json',
    jsonBody: expr("{{ { model: 'text-embedding-3-small', input: $('Input').item.json.question_text, dimensions: 1536, encoding_format: 'float' } }}"),
    options: { timeout: 60000, response: { response: { fullResponse: true, neverError: true, responseFormat: 'json' } } },
  } },
});

const succeeded = ifElse({ version: 2.3, config: { name: 'Embedding succeeded?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('OpenAI embedding — paid').item.json.statusCode }}"), rightValue: 200, operator: { type: 'number', operation: 'equals' } },
  ] },
} } });

const hasStatus = ifElse({ version: 2.3, config: { name: 'Provider returned HTTP status?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($('OpenAI embedding — paid').item.json.statusCode || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const reconcile = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reconcile embedding cost', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O2721VLonNSui2TW' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Input').item.json.attempt_id }}"),
      actual_cost_usd: expr("{{ (($('OpenAI embedding — paid').item.json.body.usage?.total_tokens || 0) * $('Input').item.json.input_cost_per_million_usd) / 1000000 }}"),
      reported_model: expr("{{ $('OpenAI embedding — paid').item.json.body.model || 'text-embedding-3-small' }}"),
      usage: expr("{{ $('OpenAI embedding — paid').item.json.body.usage || {} }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'actual_cost_usd', displayName: 'actual_cost_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reported_model', displayName: 'reported_model', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'usage', displayName: 'usage', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const storeAndFind = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Store vector and retrieve top 10', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.store_candidate_embedding_and_find($1::uuid, $2::vector);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.candidate_id, JSON.stringify($('OpenAI embedding — paid').item.json.body.data[0].embedding)] }}") },
  } },
});

const release = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Release definite failure reservation', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'z0kaN1S9ci6Ekn1R' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'http_error', status_code: $('OpenAI embedding — paid').item.json.statusCode, message: $('OpenAI embedding — paid').item.json.body?.error?.message || 'Embedding request failed' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const unknown = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Record ambiguous embedding spend', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'DsoqFjpqv1mhOQU8' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'ambiguous_transport', message: $('OpenAI embedding — paid').item.json.error?.message || $('OpenAI embedding — paid').item.json.message || 'Embedding transport result unknown' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const persistTrace = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist embedding invocation trace', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select * from qb3.persist_agent_run($1,$2,$3,$4::uuid,$5::uuid,null::uuid,'embedding','embedding','v1',$6,$7,$8::jsonb,$9,null);",
    options: { queryReplacement: expr("{{ (() => { const response = $('OpenAI embedding — paid').item.json; const ok = response.statusCode === 200; const stored = ok ? $('Store vector and retrieve top 10').item.json : {}; return [$('Input').item.json.attempt_id, $('Input').item.json.attempt_id, $('Input').item.json.campaign_id, $('Input').item.json.batch_id, $('Input').item.json.candidate_id, $('Input').item.json.question_text, JSON.stringify({ statusCode: response.statusCode || null, model: response.body?.model || 'text-embedding-3-small', usage: response.body?.usage || {}, error: response.body?.error || response.error || response.message || null }), JSON.stringify(ok ? { status: 'succeeded', candidate_id: stored.candidate_id, neighbours: stored.neighbours || [] } : { status: 'failed', candidate_id: $('Input').item.json.candidate_id, transport_status: String(response.statusCode || '') ? 'retryable_failure' : 'failed' }), ok ? 'succeeded' : 'failed']; })() }}") },
  } },
});

const traceSucceeded = ifElse({ version: 2.3, config: { name: 'Traced embedding succeeded?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('OpenAI embedding — paid').item.json.statusCode }}"), rightValue: 200, operator: { type: 'number', operation: 'equals' } },
  ] },
} } });

const returnStored = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return stored embedding result', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'stored-status', name: 'status', value: 'succeeded', type: 'string' },
    { id: 'stored-candidate', name: 'candidate_id', value: expr("{{ $('Store vector and retrieve top 10').item.json.candidate_id }}"), type: 'string' },
    { id: 'stored-neighbours', name: 'neighbours', value: expr("{{ $('Store vector and retrieve top 10').item.json.neighbours || [] }}"), type: 'array' },
  ] } } },
});

const returnFailure = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return traced embedding failure', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'failed-status', name: 'status', value: 'failed', type: 'string' },
    { id: 'failed-reason', name: 'reason', value: expr("{{ String($('OpenAI embedding — paid').item.json.statusCode || '') ? 'embedding_provider_failure' : 'embedding_transport_unknown' }}"), type: 'string' },
    { id: 'failed-candidate', name: 'candidate_id', value: expr("{{ $('Input').item.json.candidate_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Idempotent paid embedding\nReserve before calling OpenAI. A completed attempt returns its persisted result; a duplicate worker stops while the original lease is active; every provider success or failure is traced before returning to the caller.', [reserve, existingResult, embed, persistTrace, returnCached, stopDuplicateWorker, returnFailure], { color: 4 });

export default workflow('qb3-embed-retrieve', 'Embed and retrieve neighbours')
  .add(input)
  .to(reserve)
  .to(existingResult
    .onTrue(returnCached.to(stopDuplicateWorker))
    .onFalse(reserved
      .onTrue(embed.to(succeeded
        .onTrue(reconcile.to(storeAndFind).to(persistTrace).to(traceSucceeded
          .onTrue(returnStored)
          .onFalse(returnFailure)))
        .onFalse(hasStatus
          .onTrue(release.to(persistTrace).to(traceSucceeded
            .onTrue(returnStored)
            .onFalse(returnFailure)))
          .onFalse(unknown.to(persistTrace).to(traceSucceeded
            .onTrue(returnStored)
            .onFalse(returnFailure))))))
      .onFalse(returnUnavailable)))
  .add(note);
