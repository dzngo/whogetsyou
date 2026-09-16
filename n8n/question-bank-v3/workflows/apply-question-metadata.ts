import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'candidate_id', type: 'string' }, { name: 'metadata', type: 'object' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply metadata transaction', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.apply_question_metadata($1::uuid, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.candidate_id, JSON.stringify($('Input').item.json.metadata || {})] }}") },
  } },
});

export default workflow('qb3-apply-question-metadata', 'Apply question metadata').add(input).to(query);
