import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const failure = trigger({
  type: 'n8n-nodes-base.errorTrigger', version: 1,
  config: { name: 'Question Bank workflow failed', parameters: {} },
});

const persist = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist sanitized failure', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `with context as materialized (
      select campaign_id from qb3.workflow_execution_context where execution_id = $2
    ), stopped as (
      update qb3.campaigns set status = 'database_error', completed_at = now()
      where campaign_id = (select campaign_id from context) and status = 'running'
      returning campaign_id
    ), released as (
      delete from qb3.campaign_worker_leases
      where campaign_id = (select campaign_id from context) and execution_id = $2
      returning campaign_id
    )
    insert into qb3.workflow_errors (
      campaign_id, workflow_id, execution_id, node_name, sanitized_error
    ) values (
      (select campaign_id from context), $1, $2, $3,
      jsonb_build_object(
        'name', $4,
        'message', $5,
        'campaign_stopped', exists(select 1 from stopped),
        'worker_released', exists(select 1 from released)
      )
    ) returning workflow_error_id, campaign_id, created_at;`,
    options: { queryReplacement: expr("{{ [$('Question Bank workflow failed').item.json.workflow?.id || '', $('Question Bank workflow failed').item.json.execution?.id || '', $('Question Bank workflow failed').item.json.execution?.lastNodeExecuted || '', $('Question Bank workflow failed').item.json.execution?.error?.name || 'WorkflowError', $('Question Bank workflow failed').item.json.execution?.error?.message || 'Unknown workflow error'] }}") },
  } },
});

export default workflow('qb3-error-handler', 'Handle Question Bank workflow errors').add(failure).to(persist);
