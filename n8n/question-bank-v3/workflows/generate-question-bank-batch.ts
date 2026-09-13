import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Batch generation input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'requested_level_mix', type: 'object' }, { name: 'distribution_snapshot', type: 'object' },
  ] } } },
});

const observation = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '1. Observation Agent', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'qD5JTSZIaxP0NRrc' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-observation' }}"),
      invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-observation' }}"),
      context: expr("{{ { distribution_snapshot: $('Batch generation input').item.json.distribution_snapshot, requested_level_mix: $('Batch generation input').item.json.requested_level_mix } }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const observationOk = ifElse({ version: 2.3, config: { name: 'Observation usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const missions = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '2. Mission Writer Agent', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'JIBSpOL8iNrdStob' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-missions' }}"),
      invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-missions' }}"),
      context: expr("{{ { observation: $('1. Observation Agent').item.json.structured_response, requested_level_mix: $('Batch generation input').item.json.requested_level_mix } }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const missionsOk = ifElse({ version: 2.3, config: { name: 'Missions usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const splitMissions = node({
  type: 'n8n-nodes-base.splitOut', version: 1,
  config: { name: 'Split four missions', parameters: {
    fieldToSplitOut: 'structured_response.missions', include: 'noOtherFields', options: { destinationFieldName: 'mission' },
  } },
});

const missionLoop = splitInBatches({ version: 3, config: { name: 'Run four Creative agents sequentially', parameters: { batchSize: 1 } } });

const creative = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '3. Creative Agent — five questions', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'd13B7MoLCnjxwcrm' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), candidate_id: '', mission_id: '',
      attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $json.mission.mission_slot }}"),
      invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $json.mission.mission_slot }}"),
      context: expr("{{ { mission: $json.mission, observation: $('1. Observation Agent').item.json.structured_response } }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const creativeOk = ifElse({ version: 2.3, config: { name: 'Creative output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const persist = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist mission and five candidates', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '9zwD0MEaJba33INb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"),
      mission_slot: expr("{{ $('Split four missions').item.json.mission.mission_slot }}"),
      level: expr("{{ $('Split four missions').item.json.mission.level }}"),
      observation_report: expr("{{ $('1. Observation Agent').item.json.structured_response }}"),
      mission: expr("{{ $('Split four missions').item.json.mission }}"),
      questions: expr("{{ $('3. Creative Agent — five questions').item.json.structured_response.questions }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'mission_slot', displayName: 'mission_slot', type: 'number' }, { id: 'level', displayName: 'level', type: 'string' },
      { id: 'observation_report', displayName: 'observation_report', type: 'object' }, { id: 'mission', displayName: 'mission', type: 'object' },
      { id: 'questions', displayName: 'questions', type: 'array' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const generationFailed = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return generation provider failure', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'operationally_unresolved', type: 'string' },
    { id: 'stage', name: 'stage', value: 'generation', type: 'string' },
  ] } } },
});

const generated = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Return persisted candidate count', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: "select 'generated'::text as status, count(*)::integer as candidate_count from qb3.candidates where batch_id = $1::uuid;",
    options: { queryReplacement: expr("{{ [$('Batch generation input').item.json.batch_id] }}") },
  } },
});

const note = sticky('## Generation\nObservation and Mission Writer run once. Four dynamic missions then call one reusable Creative Agent sequentially, five questions each. Every successful mission is persisted immediately.', [observation, missions, splitMissions, missionLoop, creative, persist], { color: 5 });

export default workflow('qb3-generate-batch', 'Generate Question Bank batch candidates')
  .add(input).to(observation).to(observationOk
    .onTrue(missions.to(missionsOk
      .onTrue(splitMissions.to(missionLoop
        .onEachBatch(creative.to(creativeOk
          .onTrue(persist.to(nextBatch(missionLoop)))
          .onFalse(nextBatch(missionLoop))))
        .onDone(generated)))
      .onFalse(generationFailed)))
    .onFalse(generationFailed))
  .add(note);
