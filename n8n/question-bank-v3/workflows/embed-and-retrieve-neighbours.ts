import { workflow, node, trigger, newCredential, expr, ifElse } from '@n8n/workflow-sdk';

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
    { leftValue: expr('{{ $json.reserved }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ] },
} } });

const embed = node({
  type: 'n8n-nodes-base.httpRequest', version: 4.4,
  config: { name: 'OpenAI embedding — paid', onError: 'continueRegularOutput', credentials: {
    httpTemplatedCustomAuth: newCredential('Question Bank v3 OpenAI HTTP'),
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
    { leftValue: expr('{{ $json.statusCode }}'), rightValue: 200, operator: { type: 'number', operation: 'equals' } },
  ] },
} } });

const hasStatus = ifElse({ version: 2.3, config: { name: 'Provider returned HTTP status?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($json.statusCode || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
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
  config: { name: 'Store vector and retrieve top 10', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
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

export default workflow('qb3-embed-retrieve', 'Embed and retrieve neighbours')
  .add(input)
  .to(reserve)
  .to(reserved.onTrue(
    embed.to(succeeded
      .onTrue(reconcile.to(storeAndFind))
      .onFalse(hasStatus.onTrue(release).onFalse(unknown)))
  ));
