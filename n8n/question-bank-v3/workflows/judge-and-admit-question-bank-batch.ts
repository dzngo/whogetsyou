import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Semantic stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const workTokens = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Create semantic work tokens', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "with eligible_count as materialized (select count(*)::integer as item_count from qb3.candidates c join qb3.campaigns campaign using (campaign_id) where c.batch_id = $1::uuid and c.state = 'proposed' and c.quality_result ->> 'verdict' = 'pass' and c.embedding is not null and c.semantic_result is null and campaign.status = 'running' and not campaign.cancel_requested and ((c.level = 'shallow' and campaign.accepted_shallow < campaign.shallow_target) or (c.level = 'deep' and campaign.accepted_deep < campaign.deep_target))), tokens as materialized (select g as work_token from eligible_count e cross join lateral generate_series(1, e.item_count) g) select work_token, true as has_items from tokens union all select 0, false where not exists (select 1 from tokens) order by work_token;",
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id] }}") },
  } },
});

const workAvailable = ifElse({ version: 2.3, config: { name: 'Any semantic work?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const semanticLoop = splitInBatches({ version: 3, config: { name: 'Judge each semantic candidate', parameters: { batchSize: 1 } } });

const nextCandidate = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read next candidate with fresh neighbours', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: `with candidate as materialized (
      select c.*
      from qb3.candidates c
      join qb3.campaigns campaign using (campaign_id)
      where c.batch_id = $1::uuid
        and c.state = 'proposed'
        and c.quality_result ->> 'verdict' = 'pass'
        and c.embedding is not null
        and c.semantic_result is null
        and campaign.status = 'running'
        and not campaign.cancel_requested
        and (
          (c.level = 'shallow' and campaign.accepted_shallow < campaign.shallow_target)
          or (c.level = 'deep' and campaign.accepted_deep < campaign.deep_target)
        )
      order by c.candidate_index
      limit 1
    ), candidate_input as (
      select jsonb_build_array(jsonb_build_object(
        'candidate_id', c.candidate_id,
        'question', c.question_text,
        'level', c.level,
        'nearest_questions', coalesce((
          select jsonb_agg(to_jsonb(n) order by n.cosine_distance)
          from qb3.find_nearest_questions(c.embedding, 10) n
        ), '[]'::jsonb)
      )) as candidates
      from candidate c
    )
    select 1 as group_index, candidates, true as has_items from candidate_input
    union all select 0, '[]'::jsonb, false where not exists (select 1 from candidate_input);`,
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id] }}") },
  } },
});

const candidateAvailable = ifElse({ version: 2.3, config: { name: 'Candidate available?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const judge = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '6. Semantic Judge', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2qXLFcVT39XE9GG1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Semantic stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Semantic stage input').item.json.batch_id }}"),
      candidate_id: expr("{{ $('Read next candidate with fresh neighbours').item.json.candidates[0].candidate_id }}"), mission_id: '',
      attempt_id: expr("{{ $('Semantic stage input').item.json.batch_id + '-semantic-' + $('Read next candidate with fresh neighbours').item.json.candidates[0].candidate_id }}"),
      invocation_id: expr("{{ $('Semantic stage input').item.json.batch_id + '-semantic-' + $('Read next candidate with fresh neighbours').item.json.candidates[0].candidate_id }}"),
      context: expr("{{ { candidates: $('Read next candidate with fresh neighbours').item.json.candidates } }}"),
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
    { leftValue: expr("{{ $json.structured_response?.decisions?.length || 0 }}"), rightValue: expr("{{ $('Read next candidate with fresh neighbours').item.json.candidates.length }}"), operator: { type: 'number', operation: 'equals' } },
  ],
} } } });

const apply = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply semantic decisions and admit distinct', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_semantic_results($1::uuid, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id, JSON.stringify(($('6. Semantic Judge').item.json.structured_response.decisions || []).map((decision, index) => ({ ...decision, candidate_id: $('Read next candidate with fresh neighbours').item.json.candidates[index].candidate_id })))] }}") },
  } },
});

const markGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed semantic group', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "select count(*)::integer as marked_count from qb3.mark_candidates_operationally_unresolved($1::uuid, $2::jsonb, 'semantic', 'Semantic provider attempts failed');",
    options: { queryReplacement: expr("{{ [$('Semantic stage input').item.json.batch_id, JSON.stringify($('Read next candidate with fresh neighbours').item.json.candidates.map(c => c.candidate_id))] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Semantic stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'semantic_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Semantic stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Semantic admission\nEvery candidate, including the first candidate in an empty bank, is judged by the Semantic Judge. An empty bank supplies nearest_questions: []. Candidates are processed one at a time and neighbours are queried immediately before each judgment, so every same-campaign acceptance is visible to the next candidate. The decision count must match the input, and opaque candidate IDs are restored before PostgreSQL accepts, rejects, or queues review.', [workTokens, semanticLoop, nextCandidate, judge, apply, markGroup], { color: 3 });

export default workflow('qb3-semantic-admission-stage', 'Judge and admit Question Bank batch')
  .add(input).to(workTokens).to(workAvailable
    .onTrue(semanticLoop
      .onEachBatch(nextCandidate.to(candidateAvailable
        .onTrue(judge.to(judgeOk
          .onTrue(apply.to(nextBatch(semanticLoop)))
          .onFalse(markGroup.to(nextBatch(semanticLoop)))))
        .onFalse(done)))
      .onDone(done))
    .onFalse(done))
  .add(note);
