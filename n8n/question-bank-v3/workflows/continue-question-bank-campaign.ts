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
    query: `with recorded as (insert into qb3.workflow_execution_context (execution_id, workflow_id, campaign_id)
      values ($1, $2, $3)
      on conflict (execution_id) do update set campaign_id = excluded.campaign_id
      returning campaign_id)
      select campaign_id, $1::text as worker_execution_id,
             qb3.claim_campaign_worker(campaign_id, $1) as claimed
      from recorded;`,
    options: { queryReplacement: expr("{{ [$execution.id, $workflow.id, $('Campaign continuation input').first().json.campaign_id] }}") },
  } },
});

const workerClaimed = ifElse({ version: 2.3, config: { name: 'Sole campaign worker?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.claimed }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const recoveryTokens = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Count unfinished metadata groups first', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `with due as (
      select c.batch_id, count(*) as due_count
      from qb3.candidates c
      join qb3.candidate_stage_work w
        on w.candidate_id = c.candidate_id and w.stage = 'metadata'
      where c.campaign_id = $1 and c.state = 'accepted'
        and c.metadata_result is null
        and w.status in ('pending', 'retry_wait')
        and (w.next_retry_at is null or w.next_retry_at <= now())
        and w.attempt_count < 3
      group by c.batch_id
    ), slots as (
      select least(1000, coalesce(sum(ceil(due_count / 20.0)), 0))::integer as n
      from due
    ), tokens as (
      select g as token from slots cross join lateral generate_series(1, slots.n) g
    )
    select token, true as has_items from tokens
    union all select 0, false where not exists (select 1 from tokens)
    order by token;`,
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id] }}") },
  } },
});

const recoveryAvailable = ifElse({ version: 2.3, config: { name: 'Recoverable metadata due?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const recoveryLoop = splitInBatches({ version: 3, config: { name: 'Resume each metadata group before generation', parameters: { batchSize: 1 } } });

const renewMetadataRecovery = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew worker before metadata recovery', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.renew_campaign_worker($1, $2) as worker_owned;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const renewQualityRecovery = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew worker before quality recovery', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.renew_campaign_worker($1, $2) as worker_owned;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const renewEmbeddingRecovery = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew worker before embedding recovery', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.renew_campaign_worker($1, $2) as worker_owned;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const renewSemanticRecovery = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew worker before semantic recovery', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.renew_campaign_worker($1, $2) as worker_owned;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const renewNewMetadataRecovery = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew worker before new metadata', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.renew_campaign_worker($1, $2) as worker_owned;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const recoverMetadata = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Recover accepted questions missing metadata', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'fVBB9c40DVvVrfGE' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      batch_id: '',
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const stageBatches = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Find unfinished candidate-stage batches', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `with due as materialized (
      select b.batch_id, b.batch_index,
        (select r from jsonb_array_elements(ps.registry_snapshot #> '{configuration,runtimes}') r
         where r ->> 'runtimeKey' = 'embedding') as embedding_runtime
      from qb3.batches b
      join qb3.campaigns c using (campaign_id)
      join qb3.prompt_snapshots ps using (prompt_snapshot_id)
      where c.campaign_id = $1
        and (qb3.stage_due_count(b.batch_id, 'quality', false) > 0
          or qb3.stage_due_count(b.batch_id, 'quality', true) > 0
          or qb3.stage_due_count(b.batch_id, 'embedding') > 0
          or qb3.stage_due_count(b.batch_id, 'semantic') > 0)
      order by b.batch_index
    )
    select batch_id, embedding_runtime, true as has_items from due
    union all select null::uuid, null::jsonb, false
      where not exists (select 1 from due);`,
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id] }}") },
  } },
});

const stageBatchesAvailable = ifElse({ version: 2.3, config: { name: 'Any candidate stages due?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const stageRecoveryLoop = splitInBatches({ version: 3, config: { name: 'Recover each existing candidate batch', parameters: { batchSize: 1 } } });

const recoverQuality = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Recover due quality decisions', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '0EGHLgoMYdCH70mQ' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      batch_id: expr("{{ $('Find unfinished candidate-stage batches').item.json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const recoverEmbedding = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Recover due embeddings', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U92MSUIKx6x2mOH7' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      batch_id: expr("{{ $('Find unfinished candidate-stage batches').item.json.batch_id }}"),
      embedding_runtime: expr("{{ $('Find unfinished candidate-stage batches').item.json.embedding_runtime }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'embedding_runtime', displayName: 'embedding_runtime', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const recoverSemantic = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Recover due semantic decisions', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'QjlOevPHtL9hBGgR' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      batch_id: expr("{{ $('Find unfinished candidate-stage batches').item.json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const recoverNewMetadata = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Finish metadata for newly admitted questions', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'fVBB9c40DVvVrfGE' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      batch_id: expr("{{ $('Find unfinished candidate-stage batches').item.json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const refreshProgress = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Recheck ready target before generation', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.refresh_campaign_recovery_status($1) as campaign_status;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id] }}") },
  } },
});

const tokens = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Create bounded internal batch tokens', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "with tokens as materialized (select g as work_token from qb3.campaigns c cross join lateral generate_series(c.next_batch_index, c.emergency_batch_ceiling) g where c.campaign_id = $1 and c.status = 'running' and not c.cancel_requested) select work_token, true as has_items from tokens union all select 0, false where not exists (select 1 from tokens) order by work_token;",
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id] }}") },
  } },
});

const tokensAvailable = ifElse({ version: 2.3, config: { name: 'Any batch tokens?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.has_items }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const campaignLoop = splitInBatches({ version: 3, config: { name: 'Continue until target, budget, cancel, or ceiling', parameters: { batchSize: 1 } } });

const renewWorker = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew exclusive campaign lease', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select qb3.claim_campaign_worker($1, $2) as claimed;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const workerStillOwned = ifElse({ version: 2.3, config: { name: 'Campaign lease still ours?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.claimed }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const processBatch = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Process next visible batch', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'VlpNeaINO6ixrWZI' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign continuation input').first().json.campaign_id }}"),
      worker_execution_id: expr("{{ $('Register campaign execution context').first().json.worker_execution_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'worker_execution_id', displayName: 'worker_execution_id', type: 'string' },
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
    operation: 'executeQuery', query: 'select qb3.release_campaign_worker($1, $2) as worker_released, s.* from qb3.campaign_status s where s.campaign_id = $1;',
    options: { queryReplacement: expr("{{ [$('Campaign continuation input').first().json.campaign_id, $('Register campaign execution context').first().json.worker_execution_id] }}") },
  } },
});

const note = sticky('## Campaign loop\nRecover accepted but unfinished questions, then due quality, embedding, and semantic work in existing batches before buying new proposals. The owning worker renews its lease between long stages. The database rechecks the Ready Question target before opening another batch.', [recoveryTokens, recoveryLoop, renewMetadataRecovery, recoverMetadata, stageBatches, stageRecoveryLoop, renewQualityRecovery, recoverQuality, renewEmbeddingRecovery, recoverEmbedding, renewSemanticRecovery, recoverSemantic, renewNewMetadataRecovery, recoverNewMetadata, refreshProgress, tokens, campaignLoop, processBatch, stillRunning, status], { color: 5 });

const candidateStageRecovery = stageBatches.to(stageBatchesAvailable
  .onTrue(stageRecoveryLoop
    .onEachBatch(renewQualityRecovery.to(recoverQuality)
      .to(renewEmbeddingRecovery).to(recoverEmbedding)
      .to(renewSemanticRecovery).to(recoverSemantic)
      .to(renewNewMetadataRecovery).to(recoverNewMetadata)
      .to(nextBatch(stageRecoveryLoop)))
    .onDone(refreshProgress))
  .onFalse(refreshProgress));

const generationLoop = tokens.to(tokensAvailable
  .onTrue(campaignLoop
    .onEachBatch(renewWorker.to(workerStillOwned
      .onTrue(processBatch.to(stillRunning
        .onTrue(nextBatch(campaignLoop))
        .onFalse(status)))
      .onFalse(status)))
    .onDone(status))
  .onFalse(status));

export default workflow('qb3-continue-campaign', 'Continue Question Bank campaign')
  .add(input.to(registerExecution).to(workerClaimed
    .onTrue(recoveryTokens.to(recoveryAvailable
    .onTrue(recoveryLoop
      .onEachBatch(renewMetadataRecovery.to(recoverMetadata).to(nextBatch(recoveryLoop)))
      .onDone(candidateStageRecovery))
    .onFalse(candidateStageRecovery)))
    .onFalse(status)))
  .add(refreshProgress.to(generationLoop))
  .add(note);
