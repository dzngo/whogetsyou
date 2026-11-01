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
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'Yji4sBytspfYXjTS' },
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
    { leftValue: expr("{{ (() => { const ms = $json.structured_response?.missions; const mix = $('Batch generation input').item.json.requested_level_mix || {}; const families = ['favorites_and_go_tos','daily_routines','personal_essentials','food_and_everyday_consumption','leisure_and_media','everyday_choices_and_spending','habits_and_quirks','mood_and_comfort','skills_and_curiosity','social_style','home_work_and_digital_life','low_stakes_situations']; const forms = ['direct','habit','reaction','hypothetical','memory']; const missionKeys = ['mission_slot','level','shallow_family','brief','routes']; const routeKeys = ['route_slot','aspect','question_form','answer_space','scenario','perspective','contrast']; if (!Array.isArray(ms) || ms.length !== 4) return false; const slots = ms.map(m => m.mission_slot).sort((a,b) => a-b); if (slots.join(',') !== '1,2,3,4') return false; const usesRoutes = ms.some(m => m.routes !== undefined); if (usesRoutes && !ms.every(m => Object.keys(m).length === missionKeys.length && missionKeys.every(k => Object.hasOwn(m, k)) && typeof m.brief === 'string' && m.brief.trim().split(/\\s+/).length <= (m.level === 'shallow' ? 12 : 16) && (m.level === 'shallow' ? families.includes(m.shallow_family) : m.shallow_family === null) && Array.isArray(m.routes) && m.routes.length === 5 && m.routes.map(r => r.route_slot).sort((a,b) => a-b).join(',') === '1,2,3,4,5' && m.routes.every(r => Object.keys(r).length === routeKeys.length && routeKeys.every(k => Object.hasOwn(r, k)) && typeof r.aspect === 'string' && r.aspect.trim().length > 2 && typeof r.answer_space === 'string' && r.answer_space.trim().length > 2 && forms.includes(r.question_form) && ['scenario','perspective','contrast'].every(k => r[k] === null || typeof r[k] === 'string')) && new Set(m.routes.map(r => r.question_form + '|' + r.answer_space.trim().toLowerCase())).size === 5)) return false; if (!usesRoutes) { const keys = ['mission_slot','level','shallow_family','brief']; if (!ms.every(m => Object.keys(m).length === keys.length && keys.every(k => Object.hasOwn(m, k)) && typeof m.brief === 'string' && m.brief.trim().split(/\\s+/).length <= (m.level === 'shallow' ? 12 : 16) && (m.level === 'shallow' ? families.includes(m.shallow_family) : m.shallow_family === null))) return false; } const shallow = ms.filter(m => m.level === 'shallow').length; const deep = ms.filter(m => m.level === 'deep').length; return shallow * 5 === Number(mix.shallow || 0) && deep * 5 === Number(mix.deep || 0); })() }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const splitMissions = node({
  type: 'n8n-nodes-base.splitOut', version: 1,
  config: { name: 'Split four missions', parameters: {
    fieldToSplitOut: 'structured_response.missions', include: 'noOtherFields', options: { destinationFieldName: 'mission' },
  } },
});

const routesPlanned = ifElse({ version: 2.3, config: { name: 'Candidate routes planned?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ Array.isArray($json.mission.routes) && $json.mission.routes.length === 5 }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const missionLoop = splitInBatches({ version: 3, config: { name: 'Plan four missions sequentially', parameters: { batchSize: 1 } } });

const planRoutes = node({ type: 'n8n-nodes-base.executeWorkflow', version: 1.3, config: { name: '3. Route Planner Agent', parameters: { mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'ywgMzrrxzslglLiI' }, workflowInputs: { mappingMode: 'defineBelow', value: {
  campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"), batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-routes-' + $('Split four missions').item.json.mission.mission_slot }}"), invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-routes-' + $('Split four missions').item.json.mission.mission_slot }}"), context: expr("{{ { mission: $('Split four missions').item.json.mission, observation: $('1. Observation Agent').item.json.structured_response } }}")
}, matchingColumns: [], schema: [{ id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' }, { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' }, { id: 'context', displayName: 'context', type: 'object' }], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true } } } });

const routesOk = ifElse({ version: 2.3, config: { name: 'Routes usable?', parameters: { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
  { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
  { leftValue: expr("{{ (() => { const rs = $json.structured_response?.routes; const forms = ['direct','habit','reaction','hypothetical','memory']; return Array.isArray(rs) && rs.length === 5 && rs.map(r => r.route_slot).sort((a,b) => a-b).join(',') === '1,2,3,4,5' && rs.every(r => typeof r.aspect === 'string' && typeof r.answer_space === 'string' && forms.includes(r.question_form) && ['scenario','perspective','contrast'].every(k => r[k] === null || typeof r[k] === 'string')) && new Set(rs.map(r => r.question_form + '|' + r.answer_space.trim().toLowerCase())).size === 5; })() }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } }
] } } } });

const pairRoutes = node({ type: 'n8n-nodes-base.set', version: 3.5, config: { name: 'Pair mission with planned routes', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
  { id: 'mission', name: 'mission', value: expr("{{ $('Split four missions').item.json.mission }}"), type: 'object' },
  { id: 'routes', name: 'routes', value: expr("{{ $('3. Route Planner Agent').item.json.structured_response.routes }}"), type: 'array' }
] } } } });

const persistMission = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist mission before Creative', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '9zwD0MEaJba33INb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"),
      mission_slot: expr("{{ $('Split four missions').item.json.mission.mission_slot }}"),
      level: expr("{{ $('Split four missions').item.json.mission.level }}"),
      observation_report: expr("{{ $('1. Observation Agent').item.json.structured_response }}"),
      mission: expr("{{ $('Split four missions').item.json.mission }}"),
      questions: expr('{{ [] }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'mission_slot', displayName: 'mission_slot', type: 'number' }, { id: 'level', displayName: 'level', type: 'string' },
      { id: 'observation_report', displayName: 'observation_report', type: 'object' }, { id: 'mission', displayName: 'mission', type: 'object' },
      { id: 'questions', displayName: 'questions', type: 'array' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const creative = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '3. Creative Agent — five questions', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'd13B7MoLCnjxwcrm' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), candidate_id: '',
      mission_id: expr("{{ $('Persist mission before Creative').item.json.mission_id }}"),
      attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $('Split four missions').item.json.mission.mission_slot }}"),
      invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $('Split four missions').item.json.mission.mission_slot }}"),
      context: expr("{{ { level: $('Split four missions').item.json.mission.level, shallow_family: $('Split four missions').item.json.mission.shallow_family, brief: $('Split four missions').item.json.mission.brief } }}"),
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
  config: { name: 'Return persisted candidate count', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: "select 'generated'::text as status, count(*)::integer as candidate_count from qb3.candidates where batch_id = $1::uuid;",
    options: { queryReplacement: expr("{{ [$('Batch generation input').item.json.batch_id] }}") },
  } },
});

const splitRoutes = node({
  type: 'n8n-nodes-base.splitOut', version: 1,
  config: { name: 'Split five candidate routes', parameters: {
    fieldToSplitOut: 'routes', include: 'allOtherFields', options: { destinationFieldName: 'route' },
  } },
});

const routeLoop = splitInBatches({ version: 3, config: { name: 'Run twenty Creative routes sequentially', parameters: { batchSize: 1 } } });

const persistRouteMission = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist mission before route Creative', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '9zwD0MEaJba33INb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"),
      mission_slot: expr("{{ $('Split five candidate routes').item.json.mission.mission_slot }}"),
      level: expr("{{ $('Split five candidate routes').item.json.mission.level }}"),
      observation_report: expr("{{ $('1. Observation Agent').item.json.structured_response }}"),
      mission: expr("{{ $('Split five candidate routes').item.json.mission }}"),
      questions: expr('{{ [] }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'mission_slot', displayName: 'mission_slot', type: 'number' }, { id: 'level', displayName: 'level', type: 'string' },
      { id: 'observation_report', displayName: 'observation_report', type: 'object' }, { id: 'mission', displayName: 'mission', type: 'object' },
      { id: 'questions', displayName: 'questions', type: 'array' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const creativeRoute = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: '3. Creative Agent — one routed question', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'd13B7MoLCnjxwcrm' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"), candidate_id: '',
      mission_id: expr("{{ $('Persist mission before route Creative').item.json.mission_id }}"),
      attempt_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $('Split five candidate routes').item.json.mission.mission_slot + '-' + $('Split five candidate routes').item.json.route.route_slot }}"),
      invocation_id: expr("{{ $('Batch generation input').item.json.batch_id + '-creative-' + $('Split five candidate routes').item.json.mission.mission_slot + '-' + $('Split five candidate routes').item.json.route.route_slot }}"),
      context: expr("{{ { level: $('Split five candidate routes').item.json.mission.level, shallow_family: $('Split five candidate routes').item.json.mission.shallow_family, brief: $('Split five candidate routes').item.json.mission.brief, route: $('Split five candidate routes').item.json.route } }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'invocation_id', displayName: 'invocation_id', type: 'string' },
      { id: 'context', displayName: 'context', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const creativeRouteOk = ifElse({ version: 2.3, config: { name: 'Routed Creative output usable?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.status || '' }}"), rightValue: 'succeeded', operator: { type: 'string', operation: 'equals' } },
    { leftValue: expr("{{ typeof $json.structured_response?.question === 'string' && $json.structured_response.question.trim().length > 2 }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const persistRouteCandidate = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist one routed candidate', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'INVwmBzSFKK7buSA' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Batch generation input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Batch generation input').item.json.batch_id }}"),
      mission_slot: expr("{{ $('Split five candidate routes').item.json.mission.mission_slot }}"),
      level: expr("{{ $('Split five candidate routes').item.json.mission.level }}"),
      observation_report: expr("{{ $('1. Observation Agent').item.json.structured_response }}"),
      mission: expr("{{ $('Split five candidate routes').item.json.mission }}"),
      route_slot: expr("{{ $('Split five candidate routes').item.json.route.route_slot }}"),
      question: expr("{{ $('3. Creative Agent — one routed question').item.json.structured_response.question }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'mission_slot', displayName: 'mission_slot', type: 'number' }, { id: 'level', displayName: 'level', type: 'string' },
      { id: 'observation_report', displayName: 'observation_report', type: 'object' }, { id: 'mission', displayName: 'mission', type: 'object' },
      { id: 'route_slot', displayName: 'route_slot', type: 'number' }, { id: 'question', displayName: 'question', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const note = sticky('## Generation\nMission Writer creates four compact territories. Route Planner then creates five controlled routes for one mission at a time, before Creative writes one question per route.', [observation, missions, splitMissions, missionLoop, planRoutes, routesOk, pairRoutes, splitRoutes, routeLoop, persistRouteMission, creativeRoute, persistRouteCandidate], { color: 5 });

export default workflow('qb3-generate-two-stage-routed-batch', 'Generate two-stage routed Question Bank batch candidates')
  .add(input).to(observation).to(observationOk
    .onTrue(missions.to(missionsOk
      .onTrue(splitMissions.to(missionLoop
        .onEachBatch(planRoutes.to(routesOk
          .onTrue(pairRoutes.to(splitRoutes.to(routeLoop
            .onEachBatch(persistRouteMission.to(creativeRoute).to(creativeRouteOk
              .onTrue(persistRouteCandidate.to(nextBatch(routeLoop)))
              .onFalse(nextBatch(routeLoop))))
            .onDone(nextBatch(missionLoop)))))
          .onFalse(nextBatch(missionLoop))))
        .onDone(generated)))
      .onFalse(generationFailed)))
    .onFalse(generationFailed))
  .add(note);
