import { workflow, node, trigger, newCredential, expr, ifElse, splitInBatches, nextBatch, sticky } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Preflight stage input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' }, { name: 'embedding_runtime', type: 'object' },
  ] } } },
});

const candidates = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Read quality-approved candidates', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: 'select * from qb3.get_preflight_candidates($1::uuid);',
    options: { queryReplacement: expr("{{ [$('Preflight stage input').item.json.batch_id] }}") },
  } },
});

const candidateLoop = splitInBatches({ version: 3, config: { name: 'Preflight and embed each candidate', parameters: { batchSize: 1 } } });

const preflight = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Exact normalized duplicate check', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'u5zkzrKytrARx5vB' },
    workflowInputs: { mappingMode: 'defineBelow', value: { candidate_id: expr('{{ $json.candidate_id }}') }, matchingColumns: [], schema: [
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const isExactDuplicate = ifElse({ version: 2.3, config: { name: 'Already in accepted bank?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr('{{ $json.exact_duplicate }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const embed = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Embed once and retrieve top ten', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '82dChxe6MtZcGnoh' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Preflight stage input').item.json.batch_id + '-embedding-' + $('Read quality-approved candidates').item.json.candidate_id }}"),
      campaign_id: expr("{{ $('Preflight stage input').item.json.campaign_id }}"), batch_id: expr("{{ $('Preflight stage input').item.json.batch_id }}"),
      candidate_id: expr("{{ $('Read quality-approved candidates').item.json.candidate_id }}"),
      question_text: expr("{{ $('Read quality-approved candidates').item.json.question_text }}"),
      reservation_usd: expr("{{ $('Preflight stage input').item.json.embedding_runtime.reservationUsd }}"),
      input_cost_per_million_usd: expr("{{ (() => { const w = $('Preflight stage input').item.json.embedding_runtime.modelWaterfall_object; const a = typeof w === 'string' ? JSON.parse(w) : w; return a[0].inputCostPerMillionUsd; })() }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string' }, { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
      { id: 'batch_id', displayName: 'batch_id', type: 'string' }, { id: 'candidate_id', displayName: 'candidate_id', type: 'string' },
      { id: 'question_text', displayName: 'question_text', type: 'string' }, { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number' },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const embeddingOk = ifElse({ version: 2.3, config: { name: 'Embedding stored?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($json.candidate_id || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
    { leftValue: expr('{{ Array.isArray($json.neighbours) }}'), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const markCandidate = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Isolate failed embedding candidate', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery', query: "select * from qb3.mark_candidates_operationally_unresolved($1::uuid, $2::jsonb, 'embedding', 'Embedding provider attempt failed or budget was unavailable');",
    options: { queryReplacement: expr("{{ [$('Preflight stage input').item.json.batch_id, JSON.stringify([$('Read quality-approved candidates').item.json.candidate_id])] }}") },
  } },
});

const done = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Preflight stage complete', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'preflight_complete', type: 'string' },
    { id: 'batch', name: 'batch_id', value: expr("{{ $('Preflight stage input').item.json.batch_id }}"), type: 'string' },
  ] } } },
});

const note = sticky('## Exact duplicate and vector retrieval\nEvery quality-approved candidate is normalized. Exact accepted-bank matches stop here. Every survivor is embedded exactly once and retrieves at most ten nearest accepted questions.', [candidates, candidateLoop, preflight, embed, markCandidate], { color: 4 });

export default workflow('qb3-preflight-embed-stage', 'Preflight and embed Question Bank batch')
  .add(input).to(candidates).to(candidateLoop
    .onEachBatch(preflight.to(isExactDuplicate
      .onTrue(nextBatch(candidateLoop))
      .onFalse(embed.to(embeddingOk
        .onTrue(nextBatch(candidateLoop))
        .onFalse(markCandidate.to(nextBatch(candidateLoop)))))))
    .onDone(done))
  .add(note);
