import { workflow, node, trigger, newCredential, expr, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Campaign worker input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
    { name: 'worker_execution_id', type: 'string' },
  ] } } },
});

const renewBeforeBatch = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Verify campaign worker before batch', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const renewBeforeQuality = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew campaign worker before quality', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const renewBeforeEmbedding = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew campaign worker before embedding', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const renewBeforeSemantic = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew campaign worker before semantic', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const renewBeforeMetadata = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew campaign worker before metadata', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const renewBeforeCompletion = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Renew campaign worker before completion', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select case when nullif($2, '') is null then true else qb3.renew_campaign_worker($1, $2) end as worker_owned;",
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id, $('Campaign worker input').first().json.worker_execution_id || ''] }}") },
  } },
});

const begin = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Begin or resume one durable batch', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.begin_next_batch($1);',
    options: { queryReplacement: expr("{{ [$('Campaign worker input').first().json.campaign_id] }}") },
  } },
});

const snapshot = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Build frozen bank distribution snapshot', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'oocwget76MOqs8Jj' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), after_batch_id: '',
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'after_batch_id', displayName: 'after_batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const context = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read immutable batch context', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: "select b.batch_id, b.requested_level_mix, ds.summary as distribution_snapshot, (select r from jsonb_array_elements(ps.registry_snapshot #> '{configuration,runtimes}') r where r ->> 'runtimeKey' = 'embedding') as embedding_runtime from qb3.batches b join qb3.campaigns c using (campaign_id) join qb3.prompt_snapshots ps using (prompt_snapshot_id) join qb3.distribution_snapshots ds on ds.distribution_snapshot_id = $2::uuid where b.batch_id = $1::uuid;",
    options: { queryReplacement: expr("{{ [$('Begin or resume one durable batch').first().json.batch_id, $('Build frozen bank distribution snapshot').first().json.distribution_snapshot_id] }}") },
  } },
});

const generate = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Stage 1 — dynamic generation', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'HKGE43o7Pv04Wxqo' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), batch_id: expr('{{ $json.batch_id }}'),
      requested_level_mix: expr('{{ $json.requested_level_mix }}'), distribution_snapshot: expr('{{ $json.distribution_snapshot }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'requested_level_mix', displayName: 'requested_level_mix', type: 'object' }, { id: 'distribution_snapshot', displayName: 'distribution_snapshot', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const quality = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Stage 2 — quality', executeOnce: true, parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '0EGHLgoMYdCH70mQ' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), batch_id: expr("{{ $('Read immutable batch context').first().json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const preflight = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Stage 3 — exact duplicate and embedding', executeOnce: true, parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U92MSUIKx6x2mOH7' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), batch_id: expr("{{ $('Read immutable batch context').first().json.batch_id }}"),
      embedding_runtime: expr("{{ $('Read immutable batch context').first().json.embedding_runtime }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'embedding_runtime', displayName: 'embedding_runtime', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const semantic = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Stage 4 — semantic judgment and admission', executeOnce: true, parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'QjlOevPHtL9hBGgR' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), batch_id: expr("{{ $('Read immutable batch context').first().json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const metadata = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Stage 5 — post-admission metadata', executeOnce: true, parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'fVBB9c40DVvVrfGE' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign worker input').first().json.campaign_id }}"), batch_id: expr("{{ $('Read immutable batch context').first().json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const complete = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Complete batch and refresh statistics', executeOnce: true, parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'JwuFxFMnXJbPsoLz' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      batch_id: expr("{{ $('Read immutable batch context').first().json.batch_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'batch_id', displayName: 'batch_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const note = sticky('## One durable batch\nThis canvas is the end-to-end control surface for one internal batch. The owning campaign worker renews its lease between long stages. Open each stage to inspect every agent input, rendered prompt, raw response, structured response, decision, and database write.', [renewBeforeBatch, begin, snapshot, context, generate, renewBeforeQuality, quality, renewBeforeEmbedding, preflight, renewBeforeSemantic, semantic, renewBeforeMetadata, metadata, renewBeforeCompletion, complete], { color: 5 });

export default workflow('qb3-process-one-batch', 'Process one Question Bank batch')
  .add(input.to(renewBeforeBatch).to(begin).to(snapshot).to(context).to(generate)
  .to(renewBeforeQuality).to(quality).to(renewBeforeEmbedding).to(preflight)
  .to(renewBeforeSemantic).to(semantic).to(renewBeforeMetadata).to(metadata)
  .to(renewBeforeCompletion).to(complete))
  .add(note);
