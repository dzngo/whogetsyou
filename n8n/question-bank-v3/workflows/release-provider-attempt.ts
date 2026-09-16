import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'attempt_id', type: 'string' },
    { name: 'sanitized_error', type: 'object' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Release in PostgreSQL', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.release_provider_attempt($1, $2::jsonb);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.attempt_id, JSON.stringify($('Input').item.json.sanitized_error || {})] }}"), largeNumbersOutput: 'text' },
  } },
});

export default workflow('qb3-release-provider-attempt', 'Release provider attempt').add(input).to(query);
