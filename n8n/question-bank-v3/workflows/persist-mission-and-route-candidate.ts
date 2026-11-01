import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Persist route candidate input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'mission_slot', type: 'number' }, { name: 'level', type: 'string' },
    { name: 'observation_report', type: 'object' }, { name: 'mission', type: 'object' },
    { name: 'route_slot', type: 'number' }, { name: 'question', type: 'string' },
  ] } } },
});

const persist = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist mission and route candidate', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.persist_mission_and_route_candidate($1, $2::uuid, $3::integer, $4, $5::jsonb, $6::jsonb, $7::integer, $8);',
    options: { queryReplacement: expr("{{ [ $('Persist route candidate input').item.json.campaign_id, $('Persist route candidate input').item.json.batch_id, $('Persist route candidate input').item.json.mission_slot, $('Persist route candidate input').item.json.level, JSON.stringify($('Persist route candidate input').item.json.observation_report || {}), JSON.stringify($('Persist route candidate input').item.json.mission || {}), $('Persist route candidate input').item.json.route_slot, $('Persist route candidate input').item.json.question ] }}") },
  } },
});

export default workflow('qb3-persist-route-candidate', 'Persist one planned route candidate')
  .add(input).to(persist);
