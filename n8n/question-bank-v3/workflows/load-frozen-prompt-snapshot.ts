import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
    { name: 'prompt_key', type: 'string' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Load immutable prompt', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.load_frozen_prompt($1, $2);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.campaign_id, $('Input').item.json.prompt_key] }}") },
  } },
});

export default workflow('qb3-load-frozen-prompt', 'Load frozen prompt snapshot').add(input).to(query);
