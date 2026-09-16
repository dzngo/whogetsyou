import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Campaign continuation input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
  ] } } },
});

const registerExecution = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Register campaign execution context', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `insert into qb3.workflow_execution_context (execution_id, workflow_id, campaign_id)
      values ($1, $2, $3)
      on conflict (execution_id) do update set campaign_id = excluded.campaign_id
      returning campaign_id;`,
    options: { queryReplacement: expr("{{ [$execution.id, $workflow.id, $('Campaign continuation input').item.json.campaign_id] }}") },
  } },
});

const tokens = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Create bounded internal batch tokens', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "with tokens as materialized (select g as work_token from qb3.campaigns c cross join lateral generate_series(c.next_batch_index, c.emergency_batch_ceiling) g where c.campaign_id = $1 and c.status = 'running' and not c.cancel_requested) select work_token, true as has_items from tokens union all select 0, false where not exists (select 1 from tokens) order by work_token;",
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').item.json.campaign_id] }}") },
  } },
});

const tokensAvailable = ifElse({ version: 2.3, config: { name: 'Any batch tokens?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const campaignLoop = splitInBatches({ version: 3, config: { name: 'Continue until target, budget, cancel, or ceiling', parameters: { batchSize: 1 } } });

const processBatch = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Process next visible batch', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'VlpNeaINO6ixrWZI' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').item.json.campaign_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const stillRunning = ifElse({ version: 2.3, config: { name: 'Another batch allowed?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $json.campaign_status || '' }}"), rightValue: 'running', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const status = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Return durable campaign status', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.campaign_status where campaign_id = $1;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').item.json.campaign_id] }}") },
  } },
});

const note = sticky('## Campaign loop\nA campaign is the operator-visible job. Internal batches are bounded by a durable emergency ceiling and continue only while the database reports running. Every batch is independently resumable.', [tokens, campaignLoop, processBatch, stillRunning, status], { color: 5 });

export default workflow('qb3-continue-campaign', 'Continue Question Bank campaign')
  .add(input).to(registerExecution).to(tokens).to(tokensAvailable
    .onTrue(campaignLoop
      .onEachBatch(processBatch.to(stillRunning
        .onTrue(nextBatch(campaignLoop))
        .onFalse(status)))
      .onDone(status))
    .onFalse(status))
  .add(note);
