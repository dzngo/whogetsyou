# Question Bank v3 reliability and resume plan

Status: implemented and deployed. Migration `010_question_stage_progress.sql`
is applied to the production database, the recovery workflows are published,
and the disposable SQL contract suite passes. This plan changes the existing
n8n v3 system incrementally. It does not authorize a paid run by itself.

Verification evidence: `./test-sql.sh` applies the upgrade twice in an isolated
PostgreSQL container and covers partial metadata, duplicate replay, a
pre-send crash, a post-send lost response, quality/embedding/semantic recovery,
separate escalation retry allowance, worker ownership, and a provider-wide 503
pause. `./scripts/preflight-recovery-deployment.sh qb3-2871` captures the
pre-deployment production ledger without changing it. Workflow SDK validation
is also required before live update and publish.

## Outcome

A campaign survives provider errors, n8n restarts, and partial AI output
without losing accepted questions or buying the same attempt twice. Every
question has durable progress. A campaign reaches its target using **Ready
Questions** (accepted and metadata-complete), not merely admitted questions.

The first production proof is the accepted questions still missing metadata in
`qb3-2871`. Re-read their count and provider ledger immediately before any
recovery: the previously observed 12 is not a hard-coded recovery list.

## Existing seams to preserve and repair

- [`qb3.candidates`](sql/001_question_bank_v3.sql) already stores the admission
  decision separately from quality, embedding, semantic, and metadata evidence.
  `accepted` must remain an admission decision, not become a processing state.
- [`qb3.questions`](sql/001_question_bank_v3.sql) is created on admission and
  can legitimately lack metadata. It remains available to duplicate detection
  while unfinished, but not to export or later gameplay use.
- [Metadata assignment](workflows/assign-question-bank-batch-metadata.ts)
  currently uses a fixed batch-scoped paid attempt ID, requires an exact
  all-or-nothing result, and reads only while the campaign is `running`.
- [Batch processing](workflows/process-one-question-bank-batch.ts) proceeds to
  completion after metadata deferral. Campaign target/counters and admission
  guards currently use accepted counts; resume requires extra budget and blocks
  certain operational failures. These rules must change together.
- The [OpenAI attempt workflow](workflows/invoke-openai-agent-attempt.ts) and
  [retry workflow](workflows/invoke-openai-agent-with-retry.ts) already have a
  provider-attempt ledger. Keep it, but distinguish retryable failures from
  configuration failures and ambiguous billable outcomes. Native n8n
  `retryOnFail` must stay **off for paid nodes**: it can make an unrecorded
  second paid call outside the reservation ledger.

## Durable per-question model

Use `candidate_id` as the stable work identity before and after admission.
Keep the existing result columns as the evidence of completed stages. Add a
small operational stage record keyed by `(candidate_id, stage)` for quality,
embedding, semantic decision, and metadata. It records:

- `pending`, `running`, `retry_wait`, `needs_attention`, or `complete`;
- attempt count, next retry time, short reason/error code, and an expiring work
  lease so a crashed worker does not leave a question permanently `running`;
- the current work-group/attempt reference, without copying question text or
  metadata into the state record.

The admission outcome stays separate and immutable. A `Ready Question` is an
accepted question with valid, atomically applied metadata; expose this via a
database view or equivalent single database predicate, rather than trusting
the n8n execution's last node. The metadata writer must update question
metadata, theme memberships, candidate evidence, and stage completion in one
transaction. Idempotent replay returns the already-applied result without
rewriting it.

Group requests still save money. Link each provider attempt to the exact set
of candidate IDs it covers. A retry has a **new** attempt/invocation ID and a
parent reference to the earlier attempt. Per-question retry limits are based
on membership in those attempts, not on the number of times an n8n node ran.

## Recovery and cost rules

1. Before any paid call, claim the stage work and reserve its maximum cost
   atomically. Only one worker can own a question-stage or campaign execution
   at a time.
2. A successful grouped response is validated item by item. Apply every valid
   item whose ID is in the request and still needs metadata. Duplicate IDs,
   unknown IDs, and invalid items are reported and left unfinished; they never
   overwrite completed questions. Return explicit applied and pending ID lists.
3. A confirmed retryable provider failure waits with backoff, then uses a new
   tracked attempt. Permit no more than two retries after the first attempt for
   each affected question-stage. Honor a provider retry delay if one is
   available. Do not retry malformed credentials, invalid configuration, or a
   prompt/schema bug as though they were transient.
4. If a request may have reached OpenAI but its response is lost, keep its
   whole reservation as **Unknown Spend** after the lease expires. Never
   replay that attempt ID. A fresh attempt may proceed automatically only if
   the remaining *existing* campaign budget covers it, counting unknown spend
   against the cap. Do not require extra authorization merely because some
   spend is unknown.
5. After the retry limit, leave the affected questions in `needs_attention`
   with a visible reason. Continue independent safe work. Pause the entire
   campaign for a code/configuration error or a persistent provider-wide
   outage, not for one bad question.
6. A periodic recovery worker may restart safe interrupted work after n8n
   restarts. It must first reconcile expired leases/attempts, respect existing
   worker claims, budget, retry limits, and cancellation, and must not create
   a second campaign. A manual Resume control remains for repaired pauses.

## Campaign and target rules

The campaign target is the number of Ready Questions per level. Keep accepted
counts for audit, and add ready counts or compute them transactionally from the
ready predicate. Update admission limits, mixed-level quotas, completion,
status output, export, and diversity statistics consistently. In particular:

- Process recoverable accepted-but-unready questions before generating new
  candidates. Do not pay to replace a question whose metadata is merely
  pending or waiting for a bounded retry.
- Generate replacements only when retry-exhausted or review-blocked questions
  can no longer satisfy the target automatically. A later manual repair could
  make a campaign exceed its minimum target; report that overage rather than
  discarding a trusted question.
- Batch completion must not imply every question is ready. It must leave
  unfinished question-stage records visible and resumable. Campaign
  `completed` requires the ready target, no unsafe in-flight attempts, and
  consistent counters.
- Resume the same campaign ID with its remaining authorized budget; an extra
  budget amount is optional, not mandatory. Recovery order: reconcile paid
  attempts; finish accepted questions missing metadata; revisit technical
  `operationally_unresolved` candidates; then generate new questions if needed.
  Genuine quality/semantic uncertainty stays in human review.

## Implementation sequence

1. **Database contract and no-cost tests.** Add the stage-work and
   attempt-membership records, a canonical ready predicate/count, guarded
   claim/lease/retry functions, and idempotent per-item metadata application.
   Make the next numbered migration the upgrade path and mirror final function
   definitions in `001_question_bank_v3.sql` for fresh installs. Backfill stage
   states from existing evidence without changing admission outcomes or
   metadata.
2. **Metadata recovery slice.** Change metadata selection so a recoverable
   stopped campaign can query exactly its missing accepted questions. Generate
   unique attempt IDs per selected group. Save valid items individually and
   retain only missing/invalid ones for retry. Wire explicit provider error
   classification and tracked backoff; never enable hidden paid-node retry.
3. **Same-campaign Resume and observability.** Update Control, campaign
   continuation, batch completion, and error handling so a recoverable pause
   is not mislabeled `database_error`. Status must show ready, accepted but
   unready, retry-wait, needs-attention, unknown-spend, remaining budget, and
   the IDs/reasons of blocked work. Add a safe periodic recovery trigger with
   a single-worker guard.
4. **Prove on `qb3-2871`.** First take a read-only snapshot of campaign,
   questions, attempts, and available budget. In a disposable database with
   mocked provider responses, exercise the exact missing-metadata shape and
   repeat Resume to prove idempotency. Validate n8n workflows and read their
   saved connections back; do not test against the live database with a
   merely pinned provider node, because downstream database writes still run.
   Only after those gates, invoke a new paid metadata attempt for the current
   missing set under the existing cap; verify per-question metadata/themes,
   ready counts, attempt ledger, and campaign status.
5. **Generalize and hand off.** Extend the same claim/checkpoint/recovery
   pattern to quality, embedding, and semantic stages; verify retryable
   `operationally_unresolved` cases re-enter their own stage without changing
   immutable admission decisions. Update the README/operator instructions and
   publish only after validation, connection readback, and representative
   no-cost tests.

## Acceptance tests

- A grouped metadata response with 8 valid of 12 items saves exactly 8; a
  resumed request contains only the remaining 4.
- Repeating Resume or the same provider callback cannot duplicate a question,
  metadata, theme membership, provider charge, or campaign count.
- A crash before send, a confirmed 429/503, a lost response after send, and a
  crash after provider success but before persistence each have distinct,
  auditable outcomes. No path silently reuses a paid attempt ID.
- Unknown spend reduces available budget at its full reserved amount. If a
  new attempt does not fit, work waits without spending or requesting a new
  campaign.
- One malformed item does not stop valid siblings; configuration failures
  stop automatic retries; two retries is the per-question-stage ceiling.
- Accepted but metadata-pending questions remain duplicate-checkable, but are
  absent from ready-only export/use and do not count toward completion.
- Concurrent recovery workers cannot claim the same question-stage; expired
  leases recover safely; cancellation stops new provider attempts.
- `qb3-2871` keeps its campaign ID and all previously accepted questions.
  Only its currently unfinished questions receive new metadata work.
