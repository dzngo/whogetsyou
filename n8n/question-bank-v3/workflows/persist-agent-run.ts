import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'invocation_id', type: 'string' },
    { name: 'attempt_id', type: 'string' },
    { name: 'campaign_id', type: 'string' },
    { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' },
    { name: 'mission_id', type: 'string' },
    { name: 'agent_role', type: 'string' },
    { name: 'prompt_key', type: 'string' },
    { name: 'prompt_version', type: 'string' },
    { name: 'rendered_prompt', type: 'string' },
    { name: 'raw_response', type: 'string' },
    { name: 'structured_response', type: 'object' },
    { name: 'status', type: 'string' },
    { name: 'repair_of_invocation_id', type: 'string' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist complete trace', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery',
    query: `select * from qb3.persist_agent_run(
      $1, $2, $3, nullif($4, '')::uuid, nullif($5, '')::uuid,
      nullif($6, '')::uuid, $7, $8, $9, $10, nullif($11, ''),
      $12::jsonb, $13, nullif($14, '')
    );`,
    options: { queryReplacement: expr("{{ [$('Input').item.json.invocation_id, $('Input').item.json.attempt_id, $('Input').item.json.campaign_id, $('Input').item.json.batch_id || '', $('Input').item.json.candidate_id || '', $('Input').item.json.mission_id || '', $('Input').item.json.agent_role, $('Input').item.json.prompt_key, $('Input').item.json.prompt_version, $('Input').item.json.rendered_prompt, $('Input').item.json.raw_response || '', JSON.stringify($('Input').item.json.structured_response || {}), $('Input').item.json.status, $('Input').item.json.repair_of_invocation_id || ''] }}") },
  } },
});

export default workflow('qb3-persist-agent-run', 'Persist agent run').add(input).to(query);
