import { workflow, node, trigger, newCredential, expr, ifElse, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Metadata stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const read = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Claim unfinished accepted questions', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: `with claimed as materialized (
      select * from qb3.claim_metadata_group($1, nullif($2, '')::uuid, 20)
    ) select * from claimed union all
      select null::text, null::uuid, '[]'::jsonb, '[]'::jsonb
      where not exists (select 1 from claimed);`,
    options: { queryReplacement: expr("{{ [$('Metadata stage input').item.json.campaign_id, $('Metadata stage input').item.json.batch_id || ''] }}") },
  } },
});

const hasQuestions = ifElse({ version: 2.3, config: { name: 'Any accepted questions?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.questions }}'), rightValue: '', operator: { type: 'array', operation: 'notEmpty', singleValue: true } },
  ],
} } } });

const metadata = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '7. Theme and Metadata Agent', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'RvIfZ87f3V1g5Hu2' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Metadata stage input').item.json.campaign_id }}"), batch_id: expr('{{ $json.batch_id }}'),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ 'metadata-' + $json.work_group_id }}"),
      invocation_id: expr("{{ 'metadata-' + $json.work_group_id }}"),
      work_group_id: expr('{{ $json.work_group_id }}'),
      context: expr('{{ { questions: $json.questions, named_themes: $json.themes } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'work_group_id', displayName: 'work_group_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const metadataOk = ifElse({ version: 2.3, config: { name: 'Metadata output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
    { leftValue: expr("{{ Array.isArray($json.structured_response?.items) }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const apply = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply valid metadata items individually', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_metadata_group_partial($1, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Claim unfinished accepted questions').item.json.work_group_id, JSON.stringify($('7. Theme and Metadata Agent').item.json.structured_response.items)] }}") },
  } },
});

const allApplied = ifElse({ version: 2.3, config: { name: 'All claimed questions ready?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ ($json.pending_ids || []).length }}'), rightValue: 0, operator: { type: 'number', operation: 'equals' } },
  ],
} } } });

const markFailure = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Record unfinished metadata group', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.finish_metadata_group_failure($1, $2, $3::boolean);',
    options: { queryReplacement: expr("{{ [$('Claim unfinished accepted questions').item.json.work_group_id, $('7. Theme and Metadata Agent').item.json.structured_response?.transport_status || $('7. Theme and Metadata Agent').item.json.reason || $('7. Theme and Metadata Agent').item.json.status || 'metadata_output_unavailable', ['retryable_failure', 'unknown_spend'].includes($('7. Theme and Metadata Agent').item.json.structured_response?.transport_status || $('7. Theme and Metadata Agent').item.json.status) || $('7. Theme and Metadata Agent').item.json.reason === 'openai_retry_exhausted'] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Metadata stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'metadata_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Metadata stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const deferred = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Metadata deferred', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'metadata_deferred', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Metadata stage input').item.json.batch_id }}"), type: 'string' },
    { id: 'reason', name: 'reason', value: 'metadata_output_incomplete_or_unavailable', type: 'string' },
  ] } } },
});

const note = sticky('## Post-admission metadata\nClaim unfinished accepted questions before every paid call. Each group has a unique tracked attempt. Valid items are committed independently; missing or invalid items remain resumable without changing admission.', [read, metadata, apply], { color: 2 });

export default workflow('qb3-metadata-stage', 'Assign Question Bank batch metadata')
  .add(input.to(read).to(hasQuestions
    .onTrue(metadata.to(metadataOk
      .onTrue(apply.to(allApplied.onTrue(done).onFalse(deferred)))
      .onFalse(markFailure.to(deferred))))
    .onFalse(done)))
  .add(note);
