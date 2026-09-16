import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'mission_slot', type: 'number' }, { name: 'level', type: 'string' },
    { name: 'observation_report', type: 'object' }, { name: 'mission', type: 'object' },
    { name: 'questions', type: 'array' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist mission and optional candidates', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.persist_mission_and_candidates($1, $2::uuid, $3::integer, $4, $5::jsonb, $6::jsonb, $7::jsonb);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.campaign_id, $('Input').item.json.batch_id, $('Input').item.json.mission_slot, $('Input').item.json.level, JSON.stringify($('Input').item.json.observation_report || {}), JSON.stringify($('Input').item.json.mission || {}), JSON.stringify($('Input').item.json.questions)] }}") },
  } },
});

export default workflow('qb3-persist-mission-candidates', 'Persist mission and candidates').add(input).to(query);
