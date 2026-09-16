import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
    { name: 'action', type: 'string' },
    { name: 'additional_budget_usd', type: 'number' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read or update campaign', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select result from qb3.campaign_command($1, $2, $3::numeric);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.campaign_id, $('Input').item.json.action, $('Input').item.json.additional_budget_usd || 0] }}"), largeNumbersOutput: 'text' },
  } },
});

export default workflow('qb3-read-update-campaign', 'Read and update campaign state').add(input).to(query);
