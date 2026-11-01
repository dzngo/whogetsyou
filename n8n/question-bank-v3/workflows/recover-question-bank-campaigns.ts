import { workflow, node, trigger, newCredential, expr, ifElse, sticky } from '@n8n/workflow-sdk';

const schedule = trigger({
  type: 'n8n-nodes-base.scheduleTrigger', version: 1.2,
  config: { name: 'Check interrupted campaigns every ten minutes', parameters: {
    rule: { interval: [{ field: 'minutes', minutesInterval: 10 }] },
  } },
});

const due = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Find safe campaign recoveries', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `select c.campaign_id
      from qb3.campaigns c
      left join qb3.campaign_worker_leases worker
        on worker.campaign_id = c.campaign_id
      join qb3.campaign_question_progress progress
        on progress.campaign_id = c.campaign_id
      where c.status in ('running', 'waiting_recovery')
        and not c.cancel_requested
        and c.reserved_usd = 0
        and c.authorized_budget_usd > c.spent_usd + c.unknown_spend_usd
        and (worker.campaign_id is null or worker.lease_expires_at <= now())
        and (exists (
          select 1 from qb3.candidate_stage_work w
          join qb3.candidates candidate using (candidate_id)
          where candidate.campaign_id = c.campaign_id
            and candidate.state = 'accepted'
            and w.stage = 'metadata'
            and w.status in ('pending', 'retry_wait')
            and (w.next_retry_at is null or w.next_retry_at <= now())
        ) or exists (
          select 1 from qb3.batches batch
          where batch.campaign_id = c.campaign_id
            and batch.status = 'running'
        ) or exists (
          select 1 from qb3.batches batch
          where batch.campaign_id = c.campaign_id
            and (qb3.stage_due_count(batch.batch_id, 'quality', false) > 0
              or qb3.stage_due_count(batch.batch_id, 'quality', true) > 0
              or qb3.stage_due_count(batch.batch_id, 'embedding') > 0
              or qb3.stage_due_count(batch.batch_id, 'semantic') > 0)
        ) or progress.ready_shallow + progress.recoverable_shallow
             + progress.recoverable_candidate_shallow < c.shallow_target
          or progress.ready_deep + progress.recoverable_deep
             + progress.recoverable_candidate_deep < c.deep_target)
      order by c.updated_at
      limit 20;`,
  } },
});

const resume = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Resume without adding budget', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select $1::text as campaign_id, qb3.resume_recoverable_campaign($1) as runnable;',
    options: { queryReplacement: expr("{{ [$json.campaign_id] }}") },
  } },
});

const runnable = ifElse({ version: 2.3, config: { name: 'Still safe to restart?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.runnable }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const worker = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Restart same campaign worker', parameters: {
    mode: 'each', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'Tn2Waxk1Btu6i4LO' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Resume without adding budget').item.json.campaign_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: false },
  } },
});

const note = sticky('## Safe catch-up after n8n restarts\nThis scheduler does not create campaigns or add authorization. It only dispatches an existing campaign with due work, remaining budget, no live provider reservation, and no active worker lease. The child takes an exclusive database lease before any paid stage.', [due, resume, runnable, worker], { color: 5 });

export default workflow('qb3-recover-campaigns', 'Recover interrupted Question Bank campaigns')
  .add(schedule.to(due).to(resume).to(runnable.onTrue(worker)))
  .add(note);
