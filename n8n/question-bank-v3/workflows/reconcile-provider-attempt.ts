import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'attempt_id', type: 'string' },
    { name: 'actual_cost_usd', type: 'number' },
    { name: 'reported_model', type: 'string' },
    { name: 'usage', type: 'object' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Reconcile in PostgreSQL', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.reconcile_provider_attempt($1, $2::numeric, $3, $4::jsonb);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.attempt_id, $('Input').item.json.actual_cost_usd, $('Input').item.json.reported_model, JSON.stringify($('Input').item.json.usage)] }}"), largeNumbersOutput: 'text' },
  } },
});

export default workflow('qb3-reconcile-provider-attempt', 'Reconcile provider attempt').add(input).to(query);
