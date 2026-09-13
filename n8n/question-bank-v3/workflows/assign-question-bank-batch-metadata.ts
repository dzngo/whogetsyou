import { workflow, node, trigger, newCredential, expr, ifElse, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Metadata stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const read = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read newly accepted questions and themes', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.get_metadata_group($1::uuid);',
    options: { queryReplacement: expr("{{ [$('Metadata stage input').item.json.batch_id] }}") },
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
      campaign_id: expr("{{ $('Metadata stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Metadata stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Metadata stage input').item.json.batch_id + '-metadata' }}"),
      invocation_id: expr("{{ $('Metadata stage input').item.json.batch_id + '-metadata' }}"),
      context: expr('{{ { questions: $json.questions, named_themes: $json.themes } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const metadataOk = ifElse({ version: 2.3, config: { name: 'Metadata output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const apply = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply themes and metadata', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_metadata_results($1::uuid, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Metadata stage input').item.json.batch_id, JSON.stringify($('7. Theme and Metadata Agent').item.json.structured_response.items)] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Metadata stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'metadata_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Metadata stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Post-admission metadata\nThemes and dimensions are assigned only after semantic admission. Metadata can never change the admission decision. If the metadata provider is unavailable, accepted questions remain accepted and can be backfilled later.', [read, metadata, apply], { color: 2 });

export default workflow('qb3-metadata-stage', 'Assign Question Bank batch metadata')
  .add(input).to(read).to(hasQuestions
    .onTrue(metadata.to(metadataOk.onTrue(apply.to(done)).onFalse(done)))
    .onFalse(done))
  .add(note);
