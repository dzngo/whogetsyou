import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Quality stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
  ] } } },
});

const qualityGroups = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read quality groups of ten', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.get_quality_groups($1::uuid, false);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id] }}") },
  } },
});

const qualityLoop = splitInBatches({ version: 3, config: { name: 'Evaluate each quality group', parameters: { batchSize: 1 } } });

const quality = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '4. Quality Judge', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'JknvnMPWaPrfrT6w' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Quality stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Quality stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Quality stage input').item.json.batch_id + '-quality-' + $json.group_index }}"),
      invocation_id: expr("{{ $('Quality stage input').item.json.batch_id + '-quality-' + $json.group_index }}"),
      context: expr('{{ { candidates: $json.candidates } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const qualityOk = ifElse({ version: 2.3, config: { name: 'Quality output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const applyQuality = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply independent quality decisions', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_quality_results($1::uuid, $2::jsonb, false);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('4. Quality Judge').item.json.structured_response.decisions)] }}") },
  } },
});

const markQualityGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed quality group', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.mark_candidates_operationally_unresolved($1::uuid, $2::jsonb, 'quality', 'Quality provider attempts failed');",
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('Read quality groups of ten').item.json.candidates.map(c => c.candidate_id))] }}") },
  } },
});

const uncertainGroups = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read uncertain quality groups', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.get_quality_groups($1::uuid, true);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id] }}") },
  } },
});

const escalationLoop = splitInBatches({ version: 3, config: { name: 'Escalate uncertain groups', parameters: { batchSize: 1 } } });

const escalation = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '5. Quality Escalation Agent', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'CY9D9PMJ56LQT9oE' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Quality stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Quality stage input').item.json.batch_id }}"),
      candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Quality stage input').item.json.batch_id + '-quality-escalation-' + $json.group_index }}"),
      invocation_id: expr("{{ $('Quality stage input').item.json.batch_id + '-quality-escalation-' + $json.group_index }}"),
      context: expr('{{ { candidates: $json.candidates } }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const escalationOk = ifElse({ version: 2.3, config: { name: 'Escalation output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const applyEscalation = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply escalation decisions', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.apply_quality_results($1::uuid, $2::jsonb, true);',
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('5. Quality Escalation Agent').item.json.structured_response.decisions)] }}") },
  } },
});

const markEscalationGroup = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed escalation group', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.mark_candidates_operationally_unresolved($1::uuid, $2::jsonb, 'quality_escalation', 'Quality escalation provider attempts failed');",
    options: { queryReplacement: expr("{{ [$('Quality stage input').item.json.batch_id, JSON.stringify($('Read uncertain quality groups').item.json.candidates.map(c => c.candidate_id))] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Quality stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'quality_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Quality stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Quality\nCandidates are judged independently in groups of ten. Only uncertain cases receive one high-reasoning escalation. Provider failure isolates that group; it does not discard other candidates.', [qualityGroups, qualityLoop, quality, applyQuality, uncertainGroups, escalationLoop, escalation, applyEscalation], { color: 6 });

export default workflow('qb3-quality-stage', 'Evaluate Question Bank batch quality')
  .add(input).to(qualityGroups).to(qualityLoop
    .onEachBatch(quality.to(qualityOk
      .onTrue(applyQuality.to(nextBatch(qualityLoop)))
      .onFalse(markQualityGroup.to(nextBatch(qualityLoop)))))
    .onDone(uncertainGroups.to(escalationLoop
      .onEachBatch(escalation.to(escalationOk
        .onTrue(applyEscalation.to(nextBatch(escalationLoop)))
        .onFalse(markEscalationGroup.to(nextBatch(escalationLoop)))))
      .onDone(done))))
  .add(note);
