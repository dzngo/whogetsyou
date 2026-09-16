import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
    { name: 'after_batch_id', type: 'string' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Build frozen snapshot', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select qb3.refresh_distribution_snapshot($1, nullif($2, '')::uuid) as distribution_snapshot_id;",
    options: { queryReplacement: expr("{{ [$('Input').item.json.campaign_id, $('Input').item.json.after_batch_id || ''] }}") },
  } },
});

export default workflow('qb3-build-distribution-snapshot', 'Build bank distribution snapshot').add(input).to(query);
