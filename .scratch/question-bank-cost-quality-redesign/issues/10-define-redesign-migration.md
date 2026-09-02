# Define Migration from the Existing Enrichment System

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Define the 20-Candidate Costed Pilot Contract](09-define-costed-pilot-contract.md)

## Question

Which current modules and immutable evidence remain useful, which topology and Coverage Plan paths are retired, how are the 248 failed-bootstrap review cases preserved but excluded, what clean storage state starts the new pilot, and what ordered migration leaves an implementation-ready path with rollback?

## Answer

The redesign uses a clean version-2 runtime and preserves the entire existing runtime as a read-only Legacy Archive. It is a replacement, not an in-place mutation or a compatibility layer over the rejected topology.

### Audited legacy state

The migration inspection on 2026-09-02 found that the live files no longer matched the earlier count of 248 review cases:

- `storage/question_bank/question_bank.sqlite3`: SHA-256 `0ed199e0dd8c1fb4eef7ed611ce3234c7ab590a5849026619cc8b0834ac978f4`, zero questions, zero revisions, zero admission packages, and zero lifecycle events;
- `storage/question_bank/workflow.sqlite3`: SHA-256 `224c8814ff23c86c4891c70b53520171c1c617a692a8cbfd9dea5f34cb94e140`, 418 open `coverage_region` Review Cases, 143 Agent Invocations, one released taxonomy version, and no Enrichment Runs, proposals, evaluation evidence, admission outcomes, theme classifications, Reference Examples, or reference regressions; and
- the 143 invocations comprise 97 succeeded, 30 cache-reused, and 16 failed records.

The extra cases are treated as later failed-bootstrap history, not as new work. At cutover, first stop all legacy writers, rerun the inventory and hashes transactionally, copy both database files into a timestamped read-only archive, and write a content-addressed Migration Manifest containing file hashes, sizes, schema/table counts, status distributions, source commit, and archive location. If the cutover inventory differs from the values above, the manifest records the actual frozen values and the operator must acknowledge the difference before continuing.

No legacy case is resolved, deleted, or converted. The version-2 CLI may expose a read-only legacy-audit command, but it must not expose legacy enrichment or review-resolution commands.

### Clean version-2 starting state

Create fresh version-2 storage rather than modifying either legacy database. Seed only:

- one empty trusted Question Bank Snapshot;
- the existing released Aspect and Perspective definitions as a versioned classification vocabulary, without Coverage Regions or completion requirements;
- current Named Theme definitions, excluding Random as a stored membership;
- the approved version-2 policies, prompts, model routing, price catalog, embedding artifact identity, and thresholds; and
- the Migration Manifest linking the clean store to the preserved legacy archive.

Do not import legacy Coverage Plans, Coverage Reports, Review Cases, invocations, cache entries, Reference Examples, proposals, draft concepts, failed-stage records, or completion state. There are no accepted legacy questions to import. Old invocation outputs are configuration-incompatible and cannot satisfy version-2 cache keys or evidence requirements.

### Retained concepts and retired topology

Retain and reshape the useful behavior behind new version-2 contracts:

- stable Question identity and immutable Question Revisions;
- lifecycle events, candidate snapshots, releases, and rollback history;
- append-only invocation, quality, semantic, metadata, review, budget, and release evidence;
- idempotent commands and successful-result caching bound to exact configuration hashes;
- the approved taxonomy vocabulary as downstream classification metadata; and
- immutable release pointer changes.

Remove these paths from the active implementation and CLI:

- four Scouts, Creative Concepts, concept deduplication, and per-question Composers;
- Coverage Planner, Coverage Region classifiers/challenger, Coverage Plan installation and generation, Coverage Reports, and gap-driven briefs;
- Completion Challenge and automated taxonomy discovery/evolution;
- four independent quality specialists plus evidence challenger;
- per-neighbour relation-call fan-out and theme-classifier challenger behavior;
- whole-bank fresh LLM release revalidation;
- automatic provider retry; and
- resolved metadata as a prerequisite for initial staging.

Delete or replace tests that assert the retired topology. Git history and the Legacy Archive provide rollback; dead runtime paths do not.

The uncommitted Coverage Horizon batching and accepted-target edits in `agents.py`, `autonomy.py`, `cli.py`, `test_agents.py`, and `test_autonomy.py` optimize the rejected system and are replaced during implementation. The independently agreed domain-document changes remain.

### Deep module and seams

Introduce one deep `EnrichmentEngine` Module as the external orchestration seam:

```text
run(request) -> RunReport
resume(run_id, new_authorization) -> RunReport
```

`RunRequest` contains the run mode, requested Levels, candidate target, USD authorization, provider-attempt limit, fixed Question Bank Snapshot, and configuration manifest. `RunReport` contains every candidate terminal state, accepted/rejected/review counts, stop reason, Cost Ledger summary, human-work summary, measured unit economics, and exact evidence/manifest identifiers.

Callers do not order stages, reserve funds, retry calls, allocate reviews, write evidence, or decide admission. The `EnrichmentEngine` implementation owns creative batching, deterministic preflight, cascaded quality evaluation, full-bank semantic routing, staging, metadata enrichment, review allocation, persistence, and stop semantics.

Provider invocation is an internal true-external seam with two real Adapter families:

- native Gemini and OpenAI Adapters for production; and
- a scripted Adapter for deterministic tests.

The Adapter interface accepts an already-reserved bounded invocation and returns either structured output plus native usage/model identity or an explicit ambiguous/definitive failure. It cannot retry or decide budgets. The Cost Ledger and durable run store remain internal Modules tested through the `EnrichmentEngine` interface using temporary SQLite storage; they are not exposed as orchestration responsibilities to callers.

Human review and release verification are separate deep Modules because they have distinct operator interfaces and lifecycles. They consume immutable engine evidence and cannot mutate a question text or reinterpret provider spend.

### Version-2 storage and cutover

- Create version-2 schemas in a new storage location with an explicit schema version; perform no `ALTER`, delete, or backfill against legacy files.
- Keep legacy paths read-only after inventory.
- Make the new CLI open version-2 storage by default only after offline verification passes.
- Refuse to open a legacy schema as writable version-2 state.
- Require exact Migration Manifest, policy, price-catalog, model, prompt, taxonomy, embedding, and threshold versions in all run and release records.
- Never reuse legacy provider cache entries.

### Ordered implementation

1. Freeze legacy writes; generate and verify the Legacy Archive and Migration Manifest.
2. Define version-2 records, schemas, configuration manifest, price catalog, Budget Reservation, Cost Ledger, and durable run-state invariants.
3. Build `EnrichmentEngine` test-first through its external interface with the scripted provider Adapter and temporary SQLite stores.
4. Add the pinned local lexical and embedding semantic scan, calibration fixture, and deterministic routing.
5. Add native Gemini and OpenAI Adapters with finite input/output bounds, native usage reconciliation, exact model-identity checks, and no retries.
6. Add bounded Review Packets, downstream metadata, Diversity Feedback, immutable reports, pilot validation, and provider-free release verification.
7. Replace the CLI and delete obsolete runtime paths and topology-specific tests.
8. Run focused tests continuously, then type/lint checks and the complete test suite; perform the required code review.
9. Commit the complete offline implementation to the current branch before any live validation.
10. Run the separate calibration and `$0.20` pilot only after explicit authorization. A passing pilot may justify requesting production authorization but cannot initiate it.

### Rollback

Before the live pilot, rollback means returning to the previous code commit and reading the untouched Legacy Archive for audit only. It never restarts legacy enrichment or provider calls. After version-2 publication, content rollback moves the immutable release pointer to an earlier verified version-2 snapshot while preserving all newer snapshots and manifests. Because no legacy file is mutated and no version-2 migration is in-place, rollback requires no destructive database reversal.
