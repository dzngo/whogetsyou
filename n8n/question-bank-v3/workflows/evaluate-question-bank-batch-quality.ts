import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Quality stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const deterministicGate = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Reject deterministic shallow form failures', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_deterministic_shallow_gate($1::uuid);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id] }}") },
  } },
});

const qualityGroups = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read quality groups of ten', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "with groups as materialized (select * from qb3.claim_candidate_stage_groups($1::uuid, 'quality', 10, false)) select group_index, work_group_id, candidates, true as has_items from groups union all select 0, null::text, '[]'::jsonb, false where not exists (select 1 from groups) order by group_index;",
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id] }}") },
  } },
});

const qualityGroupsAvailable = ifElse({ version: 2.3, config: { name: 'Any quality groups?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const qualityLoop = splitInBatches({ version: 3, config: { name: 'Evaluate each quality group', parameters: { batchSize: 1 } } });

const quality = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '4. Quality Judge', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'JknvnMPWaPrfrT6w' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Quality stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Quality stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $json.work_group_id + '-quality' }}"),
      invocation_id: expr("{{ $json.work_group_id + '-quality' }}"),
      work_group_id: expr('{{ $json.work_group_id }}'),
      context: expr('{{ { candidates: $json.candidates } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'work_group_id', displayName: 'work_group_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const qualityOk = ifElse({ version: 2.3, config: { name: 'Quality output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
    { leftValue: expr("{{ (() => { const expected = $('Read quality groups of ten').item.json.candidates.map(c => c.candidate_id).sort(); const actual = ($json.structured_response?.decisions || []).map(d => d.candidate_id).sort(); return actual.length === expected.length && new Set(actual).size === actual.length && actual.every((id, i) => id === expected[i]); })() }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const applyQuality = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply independent quality decisions', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_quality_results($1::uuid, $2::jsonb, false);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('4. Quality Judge').item.json.structured_response.decisions)] }}") },
  } },
});

const markQualityGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed quality group', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.finish_candidate_stage_group_failure($1, 'quality', $2, $3::boolean);",
    options: { queryReplacement: expr("{{ [$('Read quality groups of ten').item.json.work_group_id, $('4. Quality Judge').item.json.reason || $('4. Quality Judge').item.json.status || 'invalid_quality_output', ['retryable_failure','unknown_spend'].includes($('4. Quality Judge').item.json.status) || $('4. Quality Judge').item.json.reason === 'openai_retry_exhausted'] }}") },
  } },
});

const uncertainGroups = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read uncertain quality groups', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "with groups as materialized (select * from qb3.claim_candidate_stage_groups($1::uuid, 'quality', 10, true)) select group_index, work_group_id, candidates, true as has_items from groups union all select 0, null::text, '[]'::jsonb, false where not exists (select 1 from groups) order by group_index;",
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id] }}") },
  } },
});

const uncertainGroupsAvailable = ifElse({ version: 2.3, config: { name: 'Any uncertain groups?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const escalationLoop = splitInBatches({ version: 3, config: { name: 'Escalate uncertain groups', parameters: { batchSize: 1 } } });

const escalation = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '5. Quality Escalation Agent', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'CY9D9PMJ56LQT9oE' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Quality stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Quality stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $json.work_group_id + '-quality-escalation' }}"),
      invocation_id: expr("{{ $json.work_group_id + '-quality-escalation' }}"),
      work_group_id: expr('{{ $json.work_group_id }}'),
      context: expr('{{ { candidates: $json.candidates } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'work_group_id', displayName: 'work_group_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const escalationOk = ifElse({ version: 2.3, config: { name: 'Escalation output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
    { leftValue: expr("{{ (() => { const expected = $('Read uncertain quality groups').item.json.candidates.map(c => c.candidate_id).sort(); const actual = ($json.structured_response?.decisions || []).map(d => d.candidate_id).sort(); return actual.length === expected.length && new Set(actual).size === actual.length && actual.every((id, i) => id === expected[i]); })() }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const applyEscalation = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply escalation decisions', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_quality_results($1::uuid, $2::jsonb, true);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('5. Quality Escalation Agent').item.json.structured_response.decisions)] }}") },
  } },
});

const markEscalationGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed escalation group', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.finish_candidate_stage_group_failure($1, 'quality_escalation', $2, $3::boolean);",
    options: { queryReplacement: expr("{{ [$('Read uncertain quality groups').item.json.work_group_id, $('5. Quality Escalation Agent').item.json.reason || $('5. Quality Escalation Agent').item.json.status || 'invalid_escalation_output', ['retryable_failure','unknown_spend'].includes($('5. Quality Escalation Agent').item.json.status) || $('5. Quality Escalation Agent').item.json.reason === 'openai_retry_exhausted'] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Quality stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'quality_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Quality stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Quality\nA free deterministic gate rejects clear shallow form failures first. Remaining candidates are judged independently in groups of ten. Only uncertain cases receive one escalation.', [deterministicGate, qualityGroups, qualityLoop, quality, applyQuality, uncertainGroups, escalationLoop, escalation, applyEscalation], { color: 6 });

const escalationStage = uncertainGroups.to(uncertainGroupsAvailable
  .onTrue(escalationLoop
    .onEachBatch(escalation.to(escalationOk
      .onTrue(applyEscalation.to(nextBatch(escalationLoop)))
      .onFalse(markEscalationGroup.to(nextBatch(escalationLoop)))))
    .onDone(done))
  .onFalse(done));

const qualityStage = qualityLoop
    .onEachBatch(quality.to(qualityOk
      .onTrue(applyQuality.to(nextBatch(qualityLoop)))
      .onFalse(markQualityGroup.to(nextBatch(qualityLoop)))))
    .onDone(escalationStage);

export default workflow('qb3-quality-stage', 'Evaluate Question Bank batch quality')
  .add(input.to(deterministicGate).to(qualityGroups).to(qualityGroupsAvailable
    .onTrue(qualityStage)
    .onFalse(escalationStage)))
  .add(note);
