# Question Bank Enrichment v2 — Implementation Specification

Status: approved 2026-09-02
Supersedes: the operating topology in [`../question-bank-enrichment/implementation-specification.md`](../question-bank-enrichment/implementation-specification.md)
Source of decisions: [`map.md`](map.md) and resolved tickets 01–10

## 1. Outcome

Build an offline-operated, autonomous multi-agent system that can produce an initial release of at least 200 high-quality English questions within a hard `$2` production authorization while exposing no more than ten distinct production questions to a human.

The system optimizes variety without weakening the Question Quality Floor:

- every question is understandable and ordinarily answerable;
- every question is emotionally safe and correct for exactly one Level;
- Shallow may be a lightweight generic poll;
- Deep must invite safe, characteristic information about the Storyteller; and
- no admitted question semantically repeats the trusted bank or an earlier kept question in the same run.

The model mix is intentional:

- **Gemini Flash 3.5 with high thinking** supplies creative variation in four isolated strategy agents;
- **GPT-5.4-mini with medium reasoning** handles routine batched quality and metadata work;
- **GPT-5.4-mini with high reasoning** is reserved for genuine quality uncertainty and ambiguous semantic relations; and
- deterministic Modules alone control budgets, admission, persistence, review allocation, lifecycle, and release.

Agents are isolated structured invocations, not persistent personas. They cannot mutate trusted state, spend without a reservation, select their own model, see undeclared sibling outputs, or expose private chain-of-thought.

This specification covers bank construction, bounded review, pilot validation, and release. Gameplay sampling, adaptive retrieval, question answering, translation, automatic taxonomy evolution, and production generation itself are separate work.

## 2. Non-negotiable operating contracts

1. **Quality before count.** Budget or attempt exhaustion stops the run; it never lowers a gate.
2. **Hard authorization.** Every provider attempt obtains an atomic worst-case Budget Reservation before network I/O.
3. **No automatic retries.** An ambiguous attempt retains its full reservation as Unknown Spend.
4. **Question-only creativity.** Creative agents return finished question text, not concepts or metadata.
5. **No Theme targeting.** Theme is assigned only after quality and semantic admission.
6. **Global semantic comparison.** Initial-bank candidates are scanned against the full trusted snapshot and earlier kept candidates.
7. **Bounded human work.** Review slots are finite and operational failures never become human question cases.
8. **Provider-free release.** Release verification consumes stored compatible evidence and local projections only.
9. **Immutable evidence.** Proposals, invocations, decisions, reviews, ledger entries, revisions, snapshots, and manifests are append-only.
10. **Separate authorization.** Calibration, pilot, production, and any continuation have independent explicit budgets.

## 3. Deep Modules and interfaces

### 3.1 Enrichment Engine

The primary caller and test seam is one deep Module:

```text
run(run_request) -> run_report
resume(run_id, new_authorization) -> run_report
```

`RunRequest` contains:

- run mode: calibration, pilot, or production;
- requested Levels and candidate target;
- fixed trusted Question Bank Snapshot ID;
- USD authorization and provider-attempt limit;
- human-review allocation;
- configuration-manifest ID; and
- idempotency key.

`RunReport` contains:

- every candidate ID, exact text, Level, strategy, provenance, and terminal state;
- accepted, rejected, review, and operationally unresolved counts;
- quality, semantic, metadata, and review evidence IDs;
- stop reason and resumability;
- authorized, reserved, reconciled, Unknown Spend, and remaining exposure;
- attempts, cache hits, failures, usage, and cost per accepted question;
- yield by Level and creative strategy;
- metadata-completeness and observed-diversity reports; and
- exact input snapshot and configuration-manifest hashes.

The interface does not expose stage ordering, call batching, ledger mutation, persistence tables, review allocation, or admission rules.

### 3.2 Provider invocation seam

The engine uses an internal true-external seam:

```text
invoke(reserved_invocation) -> provider_result
```

Adapters:

- native Gemini production Adapter;
- native OpenAI Responses production Adapter; and
- scripted deterministic test Adapter.

The engine supplies an existing reservation, exact provider/model identity, structured schema, input bound, output bound, reasoning setting, prompt/policy versions, and idempotency key. An Adapter performs exactly one request and returns structured output plus native usage and reported model identity, or a definitive/ambiguous failure. It cannot retry, change models, reserve money, judge evidence, or write bank state.

### 3.3 Human Review Module

```text
open(review_packet) -> review_case
append_supplement(case_id, evidence) -> review_case
resolve(case_id, resolution) -> review_result
```

It owns immutable packet history, distinct-question slot allocation, and human resolutions. It cannot edit accepted text in place or convert operational failures into review work.

### 3.4 Release Module

```text
build(snapshot_selector) -> candidate_snapshot
verify(candidate_snapshot_id) -> release_report
publish(candidate_snapshot_id) -> release
rollback(released_snapshot_id) -> release
```

It owns manifest construction, provider-free verification, atomic release-pointer changes, withdrawal, and rollback.

### 3.5 Local semantic index

```text
scan(candidate, trusted_snapshot, earlier_kept) -> semantic_routing_evidence
rebuild(snapshot_id) -> semantic_index_manifest
```

It performs exhaustive lexical and local-embedding comparisons for the initial bank. It returns versioned routing evidence and never performs provider calls.

### 3.6 Question Usage Sink

```text
append(question_usage_event) -> append_result
```

This isolated Module retains idempotent gameplay-usage statistics for possible future adaptive retrieval. Enrichment, creativity, admission, semantic comparison, metadata, diversity feedback, and release cannot read it in this effort. Metrics loss never changes the trusted bank or blocks gameplay.

## 4. Versioned configuration manifest

Every run pins a content-addressed manifest containing:

- schema and execution versions;
- role-to-provider/model/reasoning routing;
- prompt, rubric, safety, admission, semantic, metadata, review, and release policy versions;
- input and reasoning-inclusive output limits;
- structured-output schema hashes;
- price-catalog version and freshness timestamp;
- approved Theme, Aspect, and Perspective vocabulary versions;
- embedding library/version, model ID, artifact checksum, dimensions, and normalization rules;
- lexical/embedding thresholds;
- Reference Example fixture hash; and
- source-permission policy.

Unknown, stale, unavailable, or incompatible configuration fails closed. A relevant configuration change invalidates cached provider output and release evidence.

## 5. Cost Ledger

### 5.1 Authorization

- Pilot authorization: at most `$0.20` worst-case list-price exposure and 12 actual provider attempts.
- Production authorization: at most `$2.00` exposure and 100 attempts.
- Calibration authorization: separate, initially at most `$0.50`.
- Cache hits are not attempts and record zero incremental provider spend.

The authorization is an application permission ceiling, not a prediction of the provider invoice.

### 5.2 Reservation and reconciliation

Before network I/O, the transactional ledger atomically:

1. verifies a current price entry for the exact provider/model;
2. computes worst-case input, cached-input, visible-output, and reasoning/thought exposure from finite bounds;
3. protects the remaining downstream stage allowance;
4. verifies the attempt limit; and
5. appends an active Budget Reservation.

On success, reconcile using provider-native usage and reported model identity. Release unused reservation. Apply provider cache discounts only when native usage reports them.

A timeout, interruption, crash with active reservation, unexpected model identity, or transport-ambiguous response moves the entire reservation to Unknown Spend. No automatic retry occurs. A separately authorized continuation may send a new attempt only if retained Unknown Spend plus the new reservation fit.

Concurrent workers share the same atomic ledger. The question target never overrules the remaining dollar or attempt budget.

### 5.3 Planned pilot envelope

| Stage | Attempts | Maximum reservation |
|---|---:|---:|
| Four Gemini creative batches | 4 | `$0.097200` |
| Two ordinary GPT quality batches | 2 | `$0.033750` |
| Optional high-reasoning quality escalation | 1 | `$0.034500` |
| One high-reasoning semantic batch | 1 | `$0.020250` |
| One medium-reasoning metadata batch | 1 | `$0.014175` |
| **Maximum** | **9** | **`$0.199875`** |

The unused `$0.000125` is margin, not spendable capacity. Stage maxima are reservations, not guaranteed actual cost.

## 6. End-to-end enrichment flow

```text
Run Request + fixed trusted snapshot + configuration manifest
                              |
                              v
                 atomic downstream budget plan
                              |
                              v
       4 isolated Gemini strategy agents × 5 questions
                              |
                              v
                  deterministic preflight
                              |
                              v
        2 GPT medium quality batches (stable interleave)
                              |
                 uncertainty only? -- yes --> 1 GPT high batch
                              |                         |
                              +-------------------------+
                              v
           exhaustive local lexical + embedding scan
                    |            |             |
               reject copy   local distance   ambiguous pairs
                    |            |             |
                    |            |       1 GPT high relation batch
                    |            |             |
                    +------------+-------------+
                              |
                    deterministic admission
                    |          |          |
                 Reject      Review      Stage
                                           |
                                           v
                          1 GPT medium metadata batch
                                           |
                                           v
                         stats + Diversity Feedback
                                           |
                                           v
                                  immutable Run Report
```

### 6.1 Creative agents

Bootstrap Enrichment uses four isolated Gemini Flash 3.5 high-thinking calls. Each returns exactly five non-empty, locally unique question strings:

1. **Concrete life moments** — revealing situations rather than abstract self-description.
2. **Relational mirrors** — closeness, repair, misunderstanding, and being seen.
3. **Tensions and tradeoffs** — choices where legitimate values pull apart.
4. **Inner signals** — subtle internal evidence other people may not observe.

Each agent receives only:

- requested Level;
- Question Quality Floor;
- its strategy mission;
- a compact trusted-bank avoidance summary;
- an optional bounded Diversity Feedback avoid-list from prior resolved metadata; and
- the five-question structured schema.

It receives no target Theme, Coverage Region, taxonomy matrix, sibling output, evaluator verdict, or other agent reasoning. It returns only question text. A malformed call yields no candidates from that call and is not repaired by a Composer or automatic rewrite.

### 6.2 Deterministic preflight

Reject before paid evaluation when:

- text is missing, malformed, or not one question;
- Level is invalid;
- provenance or source permission is invalid;
- normalized text duplicates the same batch, an earlier kept candidate, or the trusted snapshot; or
- required identifiers/configuration links are missing.

Preflight may flag suspicious language but cannot declare emotional safety, Level fit, Deep revelation, or semantic distinctness from keywords.

### 6.3 Cascaded quality evaluation

Stable-interleave surviving candidates across creative batches, then split into two batches of at most ten. Each `gpt-5.4-mini` medium-reasoning call has at most 4,500 input tokens and `max_output_tokens=3,000`.

For each candidate, structured evidence records exactly:

- `clarity`;
- `answerability`;
- `emotional_safety`;
- `level_fit`; and
- `deep_revelation` (`not_applicable` only for Shallow).

Each applicable field is `pass`, `fail`, or `uncertain`, with bounded reason codes and concise evidence. The deterministic resolver derives the outcome:

- any definitive failure: Reject;
- all applicable fields pass: `quality_pass`, still awaiting semantic evaluation;
- any uncertainty: candidate for selective escalation.

The model never compares candidates, ranks a batch, applies a quota, or sees strategy labels. The response must contain every requested candidate ID exactly once. Missing, duplicated, or unknown IDs invalidate the whole response and produce no trusted passes.

At most one `gpt-5.4-mini` high-reasoning call reevaluates only uncertain candidates. It sees the candidate, Level, and rubric, not the first verdict. Its bounds are 4,000 input tokens and `max_output_tokens=7,000`. It may turn uncertainty into pass or Reject; remaining uncertainty may enter bounded review. More than six ordinary uncertainties in a 20-question batch is systemic `evaluation_drift`, not six human cases.

Definitive ordinary passes and failures are never challenged merely to manufacture consensus.

### 6.4 Hybrid semantic-repetition gate

For the initial 200-question bank, scan every quality-passing candidate against:

- every active revision in the fixed trusted snapshot; and
- every earlier kept candidate in stable interleaved order.

Normalize Unicode, case, apostrophes, punctuation, and whitespace while preserving negation and content words. Record:

- token Jaccard;
- token containment;
- character-trigram cosine; and
- sentence-embedding cosine.

Use FastEmbed ONNX `BAAI/bge-small-en-v1.5`, 384 dimensions, with exact library version and artifact checksum pinned. Missing or mismatched artifacts produce `embedding_unavailable`; never substitute a paid embedding call or hashed n-gram vector.

Routing policy `semantic-routing-v1`:

- **Local Reject** when normalized text is equal; or Jaccard `>= 0.88` and character cosine `>= 0.94`; or containment `>= 0.95` and character cosine `>= 0.92`.
- **Local Distance** only when every comparison has embedding `< 0.60`, Jaccard `< 0.25`, and character cosine `< 0.55`.
- **GPT Review** for every remaining pair.

Local Distance authority remains disabled until the fresh relation fixture and pilot reviewed sample show zero false-distinct decisions. Until then, the zone prioritizes pairs but does not authorize semantic passage.

At most twelve ambiguous pairs enter one `gpt-5.4-mini` high-reasoning call with 6,000 input tokens and `max_output_tokens=3,500`. Pair overflow is an operational failure; never sample away pairs.

For every requested pair, classify Scenario, Perspective, Answer Space, Aspect, and Wording as `same`, `overlapping`, `different`, `opposed`, or `uncertain`. A semantic repeat requires Scenario, Perspective, and Answer Space all to be `same` or `overlapping`. Shared Aspect or Wording alone is insufficient.

Missing, duplicate, unknown, malformed, internally inconsistent, or ambiguous pair evidence is uncertain and can never default to distinct. A repeat rejects the candidate; distinct passes the gate; genuine uncertainty may enter bounded review.

### 6.5 Admission and Staged Question boundary

A question becomes Staged immediately after:

- valid Level, provenance, and source permission;
- complete passing quality evidence or authorized human acceptance of exact text; and
- complete semantic-distinctness evidence or authorized human acceptance of exact text.

Theme and descriptive metadata are downstream. They cannot retroactively weaken or reject a Staged Question. Human edits create a new proposal and traverse the full pipeline.

Every proposal terminates as exactly one of:

- Staged Question;
- Rejected Question Proposal;
- Awaiting Human Review; or
- Operationally Unresolved.

### 6.6 Downstream metadata

One `gpt-5.4-mini` medium-reasoning call classifies up to twenty Staged Questions with a 4,500-input-token cap and `max_output_tokens=2,400`.

For each question, return:

- zero-to-many equal Theme Memberships;
- one approved Aspect or pending;
- one approved Perspective or pending;
- bounded Semantic Scenario text or pending;
- bounded Answer Space text or pending; and
- bounded Wording Pattern text or pending.

Random is never a stored Theme Membership. A confident empty Theme set is resolved and distinct from pending. The classifier cannot invent taxonomy, challenge itself, reject admission, or trigger an automatic retry.

A schema-valid field uncertainty may create one consolidated metadata Review Packet. A malformed batch is an operational failure, not twenty review cases. If the metadata reservation cannot fit, retain Staged Questions with explicit pending fields and stop as `metadata_budget_exhausted`.

### 6.7 Observed Diversity Feedback

After at least twenty Staged Questions have resolved metadata, compute distributions locally for Level, Themes, Aspect, Perspective, clustered Scenario, clustered Answer Space, Wording Pattern, and pending rates.

Produce at most eight overrepresented patterns as an advisory avoid-list for later creative batches. It cannot create quotas, target Themes, reject questions, evolve taxonomy, or recreate Coverage Regions. Theme statistics never steer bootstrap creativity.

## 7. Human review

### 7.1 Production allocation

Across the 200-question production campaign, expose at most ten distinct questions:

- six slots for residual automated uncertainty; and
- four slots protected for release spot checking.

Unused uncertainty slots may increase the release spot check. Protected spot-check slots may not be consumed by uncertainty.

Eligible uncertainty:

- quality uncertainty after high-reasoning escalation;
- semantic uncertainty after batched high-reasoning relation evaluation; and
- field-level metadata uncertainty in an otherwise valid response.

Definitive rejections receive no review. Operational failures, pair overflow, evaluator drift, malformed batches, unavailable embeddings, budget/attempt exhaustion, unexpected model identity, and Unknown Spend never create Review Packets.

### 7.2 Packet and priority

One distinct question consumes at most one slot. Its immutable packet contains exact text, Level, provenance, snapshot and neighbour IDs, configuration versions, evidence IDs, bounded reason codes, and all known uncertainties. Supplements append later evidence without another slot.

Priority is semantic, then quality, then metadata, with stable creation order. When six uncertainty slots are exhausted:

- new quality or semantic uncertainty rejects with `review_budget_exhausted`; and
- metadata uncertainty remains Staged and pending without creating an unbounded queue.

Human admission actions are Accept or Reject exact text. Hold keeps the packet open and consumes its slot. An edit is a new proposal through the full pipeline. Metadata resolutions may choose approved values, confirm empty Themes, supply bounded descriptors, or leave fields pending.

### 7.3 Failure and resumption

Successful stage results, rejections, Staged Questions, open Review Packets, ledger entries, invocations, and failed-stage records are durable. Resumption requires a new explicit authorization, references the previous run, retains Unknown Spend, and uses stable idempotency keys. Only exact compatible successful cache entries may be reused.

## 8. Persistence and records

Use new version-2 SQLite storage as the local transactional source of truth. Lexical/embedding indexes and aggregate reports are rebuildable projections; evidence and manifests are not.

Versioned append-only records include:

- Configuration Manifest and Migration Manifest;
- Run Request, authorization, run state, and Run Report;
- Price Catalog entry, Budget Reservation, reconciliation, and Unknown Spend;
- Provider Invocation and application-cache entry;
- Question Proposal and provenance;
- Quality Evidence and deterministic quality result;
- Local Similarity Evidence, Semantic Pair Evidence, and semantic result;
- Admission Outcome and Rejection Outcome;
- Staged Question, Question identity, immutable Question Revision, and lifecycle event;
- Metadata Classification and Diversity Feedback;
- Review Packet, supplement, allocation, and human resolution;
- Reference Example fixture and regression record;
- candidate snapshot, Release Spot Check, Release Manifest, Release Report, release pointer event, withdrawal, and rollback.
- Question Usage Event in its isolated telemetry store.

Every command has an idempotency key. Every evidence record identifies its inputs and configuration by content hash. Store concise evidence and reason codes, never requested private chain-of-thought or credentials.

## 9. Release confidence

Release performs no Gemini or GPT call.

### 9.1 Frozen regression

Maintain a new frozen twelve-case human-reviewed fixture, ignoring the old eval corpus. It covers:

- good Shallow and Deep questions;
- Level failures;
- emotional-safety failures;
- semantic repeats; and
- related-but-distinct pairs.

Run it once per exact evaluator configuration under the separate calibration budget. Release requires a passing signed record matching all relevant manifest hashes.

### 9.2 Eligibility and integrity

Each released question requires resolved Level and Theme Membership; confident empty Themes are valid. Aspect, Perspective, Scenario, Answer Space, and Wording may remain pending only within the bank-wide 90% completeness rule.

Recompute and verify:

- snapshot/content hashes and one current revision per question;
- no Retired or Withdrawn revision;
- normalized-text uniqueness;
- valid provenance and source permission;
- complete accepted quality and semantic evidence;
- no open admission Review Packet;
- compatible configuration versions; and
- Cost Ledger exposure within authorization.

Rebuild the full local semantic scan. Exact/near copies block. Every pair in the GPT-review zone requires current stored `distinct` evidence. Missing, stale, repeat, or uncertain evidence blocks.

### 9.3 Anti-collapse gates

- At least 90% resolved Aspect, Perspective, Answer Space, and Wording metadata.
- No Aspect above 20%.
- No Perspective above 30%.
- No Answer Space cluster above 20%.
- No Wording Pattern above 25%.

These are observed release gates, not Theme, Level, or Cartesian generation quotas.

### 9.4 Release Spot Check

Sample size is `10 - distinct production questions already uncertainty-reviewed`, with a protected minimum of four. Half come from highest-risk locally distinct neighbour pairs; half are a deterministic spread across available Levels and creative strategies.

Any sampled quality or semantic failure blocks the entire release. Reject the failed question, diagnose the missed mode, update policy or implementation, rebuild the snapshot, and obtain a matching new regression and spot check. Do not merely delete the sampled failure and publish.

The first published snapshot contains at least 200 release-eligible questions. The pilot never publishes. Later incremental releases verify the entire resulting snapshot.

The immutable Release Manifest pins every revision, evidence record, model, prompt, policy, taxonomy, embedding artifact, threshold, ledger, regression, spot-check result, semantic index, and diversity report. Relevant changes invalidate the old regression and spot check for a new release.

## 10. Costed live pilot

The pilot is separately authorized, non-publishing, and proposes exactly twenty questions:

- ten Shallow and ten Deep;
- four creative calls, two per Level;
- all four creative strategies, with Level-to-strategy pairing rotated in later batches; and
- no Theme target or legacy review input.

It passes only when:

- exposure is at most `$0.20` and attempts at most 12;
- at least 14/20 become Staged;
- at least six accepted questions come from each Level;
- each strategy contributes at least two accepted questions;
- exposure per accepted question is at most `$0.01`;
- every Staged Question has resolved Theme Membership;
- at least 90% of Staged Questions have resolved diversity metadata;
- there is no Unknown Spend, operational failure, pair overflow, or excess admission uncertainty; and
- protected human checks find zero quality failures and zero false-distinct semantic repeats.

Pilot human exposure is at most five distinct questions: one uncertainty slot and four protected spot-check questions. Select spot checks from the two highest-risk locally distinct pairs, filling unused positions deterministically across Levels and strategies.

The immutable pilot report includes all candidate states/evidence, usage and ledger data, yield, semantic routing, metadata completeness, human results, and a pessimistic projection for 200 accepted questions. A pass only permits requesting production authorization. Any failure is `redesign_required`; no automatic paid rerun or partial scale-up occurs.

## 11. Migration and rollback

Preserve `storage/question_bank/question_bank.sqlite3` and `workflow.sqlite3` as a hashed read-only Legacy Archive. The inspected state contained zero accepted questions, 418 open Coverage Region cases, 143 invocations, and one released taxonomy version. Reinventory at cutover and require operator acknowledgment of any difference.

Version-2 starts clean with:

- an empty trusted snapshot;
- copied approved Aspect/Perspective vocabulary only;
- current Named Themes;
- version-2 configuration and price catalog; and
- the Migration Manifest.

Import no legacy Coverage Plan, review case, invocation/cache, proposal, Reference Example, or failed-run state. Never mutate legacy storage or open it as writable version-2 state.

Remove from active code and CLI:

- Scouts, Creative Concepts, concept relation, and Composers;
- Coverage Planning/Region agents and Completion Challenge;
- automatic taxonomy evolution;
- four-specialist/challenger quality fan-out;
- per-neighbour GPT fan-out;
- theme challenger;
- whole-bank LLM release revalidation; and
- all automatic retries.

Replace topology-specific tests. Git history and the Legacy Archive preserve rollback. A code rollback never restarts legacy provider work; a content rollback changes the immutable version-2 release pointer to an earlier verified snapshot.

## 12. Implementation order

1. Freeze and inventory legacy storage; create the Legacy Archive and Migration Manifest.
2. Define version-2 records, SQLite schema, configuration manifest, price catalog, and Cost Ledger.
3. Build the `EnrichmentEngine` test-first through `run` and `resume` with the scripted Adapter.
4. Add deterministic preflight and the pinned local lexical/embedding gate.
5. Add native Gemini and OpenAI Adapters with usage reconciliation and no retry.
6. Add creative, quality, semantic, staging, metadata, Diversity Feedback, and bounded review behavior.
7. Add pilot reporting, frozen-regression support, and provider-free release verification.
8. Replace the CLI and remove retired runtime paths and tests.
9. Run focused tests continuously, then static checks and the full test suite.
10. Run the required code review and commit the offline implementation on the current branch.
11. Obtain separate calibration authorization before any reference-model call.
12. Obtain separate `$0.20` authorization before the live pilot.
13. Request `$2` production authorization only after a passing pilot.

## 13. Required verification

Offline tests through Module interfaces must prove at minimum:

- atomic concurrent reservations cannot exceed authorization;
- unknown/stale prices fail before provider invocation;
- ambiguous failure retains Unknown Spend and is not retried;
- cache reuse costs zero and requires exact compatible configuration;
- creative isolation and exactly-five output validation;
- malformed batch evidence never partially passes;
- deterministic quality resolution and uncertainty-only escalation;
- full-snapshot and within-run semantic comparison;
- every routing threshold edge and pair-overflow behavior;
- semantic repeat requires Scenario + Perspective + Answer Space overlap;
- Staged creation precedes metadata and survives metadata failure;
- Theme zero-to-many semantics and Random exclusion;
- review priority, distinct-question accounting, protected slots, and exhaustion;
- idempotent resumption without duplicated calls, questions, packets, or evidence;
- provider-free release verification and evidence invalidation;
- anti-collapse gates and deterministic spot-check selection;
- pilot scale/redesign thresholds and full candidate accounting;
- clean version-2 initialization and refusal to write legacy schemas; and
- immutable publish, withdrawal, and rollback behavior.

Use temporary SQLite stores and scripted provider responses for interface tests. Native Adapter contract tests may parse recorded sanitized fixtures but must not make paid calls. A live calibration or pilot is never part of the default test suite.

## 14. Decision traceability

| Contract area | Authoritative ticket |
|---|---|
| Provider accounting facts | [`01`](issues/01-research-provider-cost-accounting.md) |
| Budget and Cost Ledger | [`02`](issues/02-define-enrichment-budget-contract.md) |
| Creative topology | [`03`](issues/03-prototype-lean-creative-batch.md) |
| Quality cascade | [`04`](issues/04-prototype-cascaded-quality-evaluation.md) |
| Semantic repetition | [`05`](issues/05-prototype-hybrid-repetition-gate.md) |
| Metadata and Diversity Feedback | [`06`](issues/06-define-post-admission-metadata-and-feedback.md) |
| Human review and failure semantics | [`07`](issues/07-define-bounded-human-review.md) |
| Release confidence | [`08`](issues/08-define-lean-release-confidence.md) |
| Costed pilot | [`09`](issues/09-define-costed-pilot-contract.md) |
| Migration and rollback | [`10`](issues/10-define-redesign-migration.md) |

The resolved ticket is authoritative if future edits accidentally make this summary ambiguous. Any deliberate contract change requires a new versioned decision rather than an unrecorded code default.
