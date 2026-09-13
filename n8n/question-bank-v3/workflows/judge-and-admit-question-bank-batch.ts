import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Semantic stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const groups = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read semantic groups of five', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.get_semantic_groups($1::uuid);',
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id] }}") },
  } },
});

const semanticLoop = splitInBatches({ version: 3, config: { name: 'Judge each semantic group', parameters: { batchSize: 1 } } });

const judge = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '6. Semantic Judge', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2qXLFcVT39XE9GG1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Semantic stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Semantic stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Semantic stage input').item.json.batch_id + '-semantic-' + $json.group_index }}"),
      invocation_id: expr("{{ $('Semantic stage input').item.json.batch_id + '-semantic-' + $json.group_index }}"),
      context: expr('{{ { candidates: $json.candidates } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const judgeOk = ifElse({ version: 2.3, config: { name: 'Semantic output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const apply = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply semantic decisions and admit distinct', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_semantic_results($1::uuid, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id, JSON.stringify($('6. Semantic Judge').item.json.structured_response.decisions)] }}") },
  } },
});

const markGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed semantic group', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.mark_candidates_operationally_unresolved($1::uuid, $2::jsonb, 'semantic', 'Semantic provider attempts failed');",
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id, JSON.stringify($('Read semantic groups of five').item.json.candidates.map(c => c.candidate_id))] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Semantic stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'semantic_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Semantic stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Semantic admission\nThe LLM sees each candidate plus only its ten nearest accepted questions. It returns an independent verdict for groups of at most five. PostgreSQL deterministically accepts, rejects, or queues review.', [groups, semanticLoop, judge, apply, markGroup], { color: 3 });

export default workflow('qb3-semantic-admission-stage', 'Judge and admit Question Bank batch')
  .add(input).to(groups).to(semanticLoop
    .onEachBatch(judge.to(judgeOk
      .onTrue(apply.to(nextBatch(semanticLoop)))
      .onFalse(markGroup.to(nextBatch(semanticLoop)))))
    .onDone(done))
  .add(note);
