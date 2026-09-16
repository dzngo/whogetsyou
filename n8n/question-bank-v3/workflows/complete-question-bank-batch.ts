import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'batch_id', type: 'string' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Complete batch and refresh evidence', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.complete_batch($1::uuid);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.batch_id] }}") },
  } },
});

export default workflow('qb3-complete-batch', 'Complete Question Bank batch').add(input).to(query);
