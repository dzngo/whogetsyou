# Automated Question Bank — Implementation Specification (Superseded)

> Superseded on 2026-09-02 by the approved [Question Bank Enrichment v2 specification](../question-bank-cost-quality-redesign/implementation-specification.md). Do not implement the legacy operating topology below. It is retained only as a design-history record.

## Outcome

Build an offline, autonomous LLM multi-agent Question Enrichment Pipeline that grows a private canonical-English Question Bank across every existing Named Theme × Level horizon. Independent creative, evaluation, classification, and challenge agents do the semantic work; deterministic Modules orchestrate them and control trusted state. Variety is the primary quality goal. Deep questions must also invite safe, characteristic personal revelation. Clear proposals are admitted or rejected automatically; only genuine uncertainty requires a person.

This specification covers the bank-building system. Runtime sampling, retrieval ranking, adaptive use of metrics, full-bank population, and gameplay integration are separate efforts.

The concrete agent roster, orchestration graph, context-isolation policy, model-selection rules, and starting logical agent count are defined in [LLM Multi-Agent System Architecture](llm-multi-agent-architecture.md). The Modules below are the stable interfaces that contain and coordinate those agents; they do not replace the agents.

## LLM Multi-Agent Architecture at a Glance

- **Proposal group:** four isolated LLM scouts explore Aspect, Scenario, Perspective, and Contrast, followed by a Concept Relation Judge and one Composer invocation per surviving concept.
- **Evaluation group:** four isolated first-pass LLM judges cover clarity/openness, Level/safety, realism/structure, and ontology, followed by per-neighbor Relation Judges and an Evidence Challenger.
- **Theme group:** a Theme Membership Classifier and Theme Classification Challenger assign resolved zero-to-many Theme Memberships after final Accept.
- **Taxonomy group:** a candidate author, independent specialist judges, an adversarial challenger, and shadow classifiers handle the stricter Aspect/Perspective evolution path.
- **Deterministic control:** the Pipeline Orchestrator, Admission Decider, Question Bank, Taxonomy Registry, Coverage Planner, and Release Module enforce ordering, idempotency, fail-closed rules, and trusted persistence.

Agents are isolated role-specific LLM invocations with versioned prompts and structured outputs. They are not persistent personas, do not share undeclared conversation history, and cannot directly mutate trusted state.

## End-to-End Flow

```text
Taxonomy Version + Coverage Plan + released bank fingerprints
                            |
                            v
                   Enrichment Brief (Level, gap)
                            |
                            v
     isolated Aspect / Scenario / Perspective / Contrast scouts
                            |
                            v
              deduplicated Creative Concepts
                            |
                            v
                 one composer per concept
                            |
                            v
                    Question Proposals
                            |
                            v
 deterministic preflight + independent specialist judgments
                            |
                            v
 whole-bank neighbor retrieval + separate relation judgments
                            |
                            v
              evidence challenge + rule decision
                 |                    |                 |
              Reject             Human review     automatic Accept
                                      |                 |
                          accept/reject/edit/hold        |
                                      |                 |
                            human Accept only ----------+
                                                        |
                                                        v
                                              Theme classification
                                                        |
                                                        v
                                              Staged Question Revision
                                                        |
                                                        v
                                       revalidation + release gates
                                                        |
                                                        v
                                         Question Bank Snapshot
```

A side path groups repeated unclassified Creative Concepts into Taxonomy Candidates. New Aspects or Perspectives enter normal proposal use only after their stricter independent evaluation, shadow classification, and Taxonomy Version release.

## Quality and Diversity Rules

Hard gates are understandable text, ordinary answerability, Bounded Openness, realism, safe framing, exactly one Level, clean single-question structure, complete permitted provenance, approved taxonomy, and global distinctness.

- Shallow may be a lightweight generic poll.
- Deep must invite characteristic but safe personal information.
- Judge only the question text; do not simulate answers.
- Classify Wording Pattern, Semantic Scenario, Question Aspect, Question Perspective, and Answer Space separately.
- A semantic repeat requires substantial overlap of Scenario, Perspective, and Answer Space; one shared facet is not enough.
- Theme is absent from creative generation and admission. Assign zero-to-many equal Theme Memberships after acceptance. Random is never stored as a membership.
- An uncertain Theme classification enters classification review before bank identity is created; only a confident empty set becomes zero memberships.
- After hard gates pass, prefer additional bank variety over extra stylistic polish.

## Modules and Interfaces

Each interface is the caller and test surface. LLM Agent graphs, prompts, indexes, storage tables, and worker topology remain inside the corresponding Module implementation. Agent roles and isolation policies remain explicit, versioned architecture even though callers do not operate individual agents directly.

### Pipeline Orchestrator Module

```text
run_enrichment(enrichment_brief) -> enrichment_run_result
```

Owns workflow ordering, idempotency, one execution retry, stage timeouts, batch identity, and movement of uncertain work to review. It does not duplicate creative, evaluation, bank, or release rules.

### Proposal Production Module

```text
propose(enrichment_brief) -> proposal_batch
```

Owns isolated scout packets, structured Creative Concepts, concept deduplication, taxonomy-expansion diversion, and one-question composition.

### Proposal Evaluation Module

```text
evaluate(question_proposal, evaluation_context) -> evaluation_result
```

Owns preflight, independent specialists, relation judgments, evidence challenge, and deterministic Accept/Reject/Human review output. It cannot create or mutate bank identity.

### Question Bank Neighbor Index Module

```text
find_neighbors(candidate_fingerprint, snapshot_id) -> neighbor_evidence
```

Owns whole-bank lexical/vector retrieval and index rebuilds. It returns high-recall candidates, never a duplicate verdict. Use a production index adapter and an exhaustive in-memory adapter for interface-level tests.

### Human Review Module

```text
open_case(review_request) -> review_case
resolve(case_id, human_resolution) -> resolution_result
```

Owns reviewer packets and immutable human resolutions for question admission, post-accept Theme classification, and taxonomy decisions. Admission Accept or Reject appends a human Admission Outcome referencing the original automatic abstention; a Theme-classification resolution records zero-to-many memberships; an edit creates a new proposal version and re-enters full evaluation.

### Taxonomy Registry Module

```text
evaluate_candidate(taxonomy_candidate, taxonomy_context) -> taxonomy_decision
release(candidate_taxonomy_version) -> taxonomy_version
```

Owns stable Aspect/Perspective IDs, aliases, definitions, examples, exclusions, deprecations, candidate evidence, and versioned changes. A candidate cannot be read by normal proposal production until release.

### Coverage Planning Module

```text
plan(taxonomy_version) -> coverage_plan
measure(snapshot_id, coverage_plan_id) -> coverage_report
next_gaps(coverage_report) -> enrichment_briefs
```

Owns Required/Exploratory/Invalid regions, the three-scenario depth floor, concentration alerts, gap ordering, and diminishing-returns challenges. It never changes Theme Membership classification to satisfy a target.

### Question Bank Module

```text
admit(accepted_question_package) -> question_revision
revise(question_id, accepted_revision_package) -> question_revision
retire(question_id, retirement) -> lifecycle_record
snapshot(snapshot_selector) -> question_bank_snapshot
```

Owns trusted Question IDs, immutable revisions, Staged/Active/Retired lifecycle, invariants, atomic persistence, and idempotent commands. No other module writes trusted bank state.

### Release Module

```text
build_candidate(release_intent) -> candidate_snapshot
verify(candidate_snapshot_id) -> release_report
publish(candidate_snapshot_id) -> question_bank_release
rollback(snapshot_id) -> question_bank_release
```

Owns frozen manifests, scoped revalidation, projection builds, release gates, content hashes, atomic current-snapshot selection, withdrawal, and rollback.

### Question Usage Sink Module

```text
append(question_usage_event) -> append_result
```

Owns idempotent telemetry delivery and validation. No enrichment, bank, coverage, release, or retrieval interface can read it in this effort.

## Core Records

Implement versioned schemas for:

- Enrichment Brief;
- Creative Concept;
- Question Proposal and Question Provenance;
- specialist judgment and facet-specific neighbor relation;
- Evaluation Evidence and Admission Outcome;
- Human Review Case and human resolution;
- Theme classification decision;
- Taxonomy Candidate, Taxonomy Version, and aliases;
- Coverage Plan, Coverage Region, and coverage report;
- Question ID, Question Revision, and lifecycle event;
- Question Bank Snapshot manifest and release report;
- Question Usage Event in its isolated telemetry store.

Every mutable workflow record carries an idempotency key and version. Every trusted or evidentiary record is append-only. Raw prompts and structured evaluator outputs link by content hash; concise reason codes are queryable without reading private chain-of-thought.

## Persistence Shape

Use a transactional relational source of truth for proposals, provenance, evidence, review, taxonomy, coverage plans, bank revisions, lifecycle events, and snapshot manifests. Treat lexical/vector indexes, semantic fingerprints, coverage reports, and aggregate metrics as rebuildable projections.

The Question Bank module owns its persistence adapter. The Question Bank Neighbor Index Module owns its index adapter. Usage events use a separate sink and retention policy. The implementation may begin with local-substitutable adapters for tests and choose the production database through deployment design without changing module interfaces.

## Autonomous Operating Loop

1. Read the current released Taxonomy Version, Coverage Plan, and coverage report.
2. Choose the highest-priority gaps while rotating across Themes, Levels, Aspects, and Perspectives.
3. Produce concepts and questions under isolated context.
4. Evaluate every proposal against a fixed released bank snapshot.
5. Reject clear failures, review uncertainty, and classify accepted questions into zero-to-many Themes.
6. Admit questions with final Accept authority and resolved Theme classification idempotently.
7. Detect repeated unclassified concepts and run the slower taxonomy path separately.
8. Periodically freeze a candidate snapshot, rebuild projections, revalidate the required scope, and publish automatically when every release gate passes.
9. Hold affected batches when a human spot check finds a recurring defect.
10. Continue until the versioned completion challenge demonstrates genuine semantic diminishing returns.

## Human Work

Initial setup requires one human to confirm roughly thirty agent-prepared Reference Examples. The first accepted batch and batches after major policy changes require a ten-question spot check. Otherwise, only uncertain proposals, uncertain post-accept Theme classifications, uncertain taxonomy changes, and discovered evaluator defects enter human review.

There is no per-question approval, routine second reviewer, agent-vote ceremony, or hidden benchmark partition. The Human Review Queue packet shows the question, classifications, provenance, concise independent evidence, closest bank relations, reason codes, and versions.

## Failure and Safety Defaults

- Missing evidence cannot Accept.
- Unknown source permission rejects before model evaluation.
- One failed stage execution retry is allowed; continued failure enters human review.
- Proposal agents never judge their own output.
- Evaluators never see peer verdicts before recording independent evidence.
- Rejected questions are not automatically paraphrased; generate a new Creative Concept.
- A candidate taxonomy cannot seed its own supporting questions.
- Partial bank writes and partial releases are impossible through atomic commands.
- Metrics loss cannot block gameplay, and metrics cannot influence the bank.

## Initial Versioned Defaults

- approximately 30 human-confirmed Reference Examples;
- 10-question spot checks for first and major-change batches;
- 1 execution retry per failed stage;
- 6 independent supporting concepts for a new Aspect or Perspective, with the cross-facet breadth defined by the taxonomy policy;
- 3 distinct Semantic Scenarios per Required Coverage Region;
- 3 completion-challenge rounds;
- at least 2 proposal strategies and at least 20 concepts per strategy in every challenge round;
- under 5% accepted distinct yield and no new valid region for every individual strategy and the combined round;
- 90-day raw Question Usage Event retention.

These values are configuration belonging to a policy version. Change them through audit evidence, not silently in code.

## Implementation Sequence

### Phase 1 — Contracts and Deterministic Core

- Define versioned record schemas and reason codes.
- Implement the Question Bank module with local-substitutable persistence.
- Implement deterministic admission, lifecycle, idempotency, and snapshot-manifest rules test-first.
- Seed Reference Examples without importing the existing eval corpus.

### Phase 2 — Proposal and Evaluation Harness

- Implement the starting LLM Agent Configuration: four isolated Creative Concept scouts, the Concept Relation Judge, and one Composer invocation per concept.
- Implement four independent evaluation specialists, per-neighbor Relation Judges, the Evidence Challenger, and abstaining deterministic decision rules.
- Persist the exact model, prompt, schema, context-policy, and execution version for every LLM Agent invocation.
- Run every topology variation against Reference Examples before adding evaluator count or debate complexity.

### Phase 3 — Review, Taxonomy, and Coverage

- Implement Human Review Queue packets and immutable resolution flow.
- Implement Taxonomy Candidate evaluation and version registry.
- Implement Coverage Plan classification, reports, gap selection, and completion challenge.

### Phase 4 — Release and Autonomous Operations

- Implement scoped revalidation, rebuildable projections, release gates, immutable snapshots, atomic publication, and rollback.
- Add scheduled enrichment runs, cost/throughput budgets, observability, and safe stop controls.
- Begin controlled bank population and use audits to tune versioned thresholds.

### Phase 5 — Separate Later Efforts

- Design Theme + Level runtime sampling and retrieval.
- Integrate a pinned trusted snapshot into gameplay.
- Implement the Question Usage Sink and, only after another decision, evaluate adaptive use.

## Verification Before Production Population

- Interface-level tests cover all module invariants and failures.
- Reference Examples produce expected Accept/Reject/Human review and relation results.
- Duplicate, paraphrase, shared-Aspect-only, shared-Perspective-only, ambiguous Deep, source-rights, missing-evidence, taxonomy-gap, retry, idempotency, and rollback scenarios pass.
- Rebuilding projections from one manifest is logically equivalent.
- A release may activate explicitly selected Staged revisions and retain existing Active revisions; it cannot include unselected staging records, Retired, queued, rejected, unlicensed, unresolved-theme, or incompletely evaluated revisions.
- Metrics are absent from every enrichment and retrieval dependency graph.
- The first human spot check passes before an initial trusted release.

## Decision Records

- [LLM multi-agent system architecture](llm-multi-agent-architecture.md)
- [Question quality contract](question-quality-contract.md)
- [Diversity ontology](diversity-ontology.md)
- [Question source and provenance](question-source-and-provenance-policy.md)
- [Human calibration and spot checks](human-calibration-and-spot-checks.md)
- [Creative proposal production](creative-proposal-production.md)
- [Automated evaluation topology](automated-evaluation-topology.md)
- [Admission and human review](admission-and-human-review.md)
- [Question Bank record and lifecycle](question-bank-record-and-lifecycle.md)
- [Automatic taxonomy evolution](automatic-taxonomy-evolution.md)
- [Coverage and completion](coverage-and-completion.md)
- [Versioning, revalidation, and release](versioning-revalidation-and-release.md)
- [Question Usage Metrics](question-usage-metrics.md)
