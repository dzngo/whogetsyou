import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const failure = trigger({
  type: 'n8n-nodes-base.errorTrigger', version: 1,
  config: { name: 'Question Bank workflow failed', parameters: {} },
});

const persist = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist sanitized failure', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery',
    query: `insert into qb3.workflow_errors (
      campaign_id, workflow_id, execution_id, node_name, sanitized_error
    ) values (
      null, $1, $2, $3, jsonb_build_object('name', $4, 'message', $5)
    ) returning workflow_error_id, created_at;`,
    options: { queryReplacement: expr("{{ [$('Question Bank workflow failed').item.json.workflow?.id || '', $('Question Bank workflow failed').item.json.execution?.id || '', $('Question Bank workflow failed').item.json.execution?.lastNodeExecuted || '', $('Question Bank workflow failed').item.json.execution?.error?.name || 'WorkflowError', $('Question Bank workflow failed').item.json.execution?.error?.message || 'Unknown workflow error'] }}") },
  } },
});

export default workflow('qb3-error-handler', 'Handle Question Bank workflow errors').add(failure).to(persist);
