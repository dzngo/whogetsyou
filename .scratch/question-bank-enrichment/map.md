# Design the Automated High-Quality Question Bank

Label: wayfinder:map
Status: resolved

## Destination

Produce an implementation-ready product and technical specification for an offline LLM multi-agent system that builds and maintains a large, high-quality canonical-English Question Bank across the existing Theme × Level space. The specification must make the automated Question Enrichment Pipeline reliable and creative enough to operate without per-question human approval, while routing genuine uncertainty to a Human Review Queue.

## Notes

- Domain: question quality and corpus construction for "Who Gets You?"; use the canonical language in [`CONTEXT.md`](../../CONTEXT.md).
- The Question Bank stores reusable full Canonical Questions; it is distinct from the Question Angle Catalog.
- Question quality includes separate relations for Question Aspect, Semantic Scenario, Question Perspective, Answer Space, and Wording Pattern.
- The normal enrichment path is fully automatic. Human-labelled benchmarks and periodic audits are allowed, and uncertain proposals go to the Human Review Queue with their evidence.
- The pipeline may use multiple models and spend minutes on offline enrichment; production gameplay must not perform live question generation for this effort.
- Agents may create questions inside the approved taxonomy and may propose new Question Aspects and Question Perspectives through a stricter automated path.
- Question Usage Metrics are collected for future analysis but do not influence the Question Bank in this effort.
- This map plans the work. Implementing the pipeline, populating the full bank, and integrating retrieval into gameplay are beyond its destination.
- Use `grilling` and `domain-modeling` for decision tickets, `prototype` for concrete examples and agent-flow tickets, `research` for external evidence, and `codebase-design` when defining module boundaries and interfaces.

## Decision index

<!-- Closed tickets are indexed here by name with a one-line gist and link. -->

- [LLM Multi-Agent System Architecture](llm-multi-agent-architecture.md): isolated role-specific LLM scouts, composers, classifiers, judges, challengers, and shadow evaluators run behind deterministic orchestration, admission, bank, taxonomy, and release Modules; model assignment is versioned and evidence-driven.
- [Define the Question Quality Contract](issues/01-define-question-quality-contract.md): Shallow permits lightweight generic polls while Deep requires safe personal revelation; after clear text, realism, safety, Level, Bounded Openness, and bank-distinctness gates pass, global variety outranks polish and Theme is assigned afterward as zero-to-many equal memberships.
- [Prototype the Diversity Ontology with Real Questions](issues/02-prototype-diversity-ontology.md): bank diversity uses global Question Aspect plus separate Semantic Scenario, Question Perspective, Answer Space, and Wording Pattern relations; Theme-owned Question Angle remains only a legacy generation aid, and no single similarity score is authoritative.
- [Define Question Source and Provenance Boundaries](issues/05-define-question-source-boundaries.md): only de novo, project-owned, explicitly contributed, or explicitly licensed sources are allowed; gameplay text and the existing eval corpus are excluded, every rewrite preserves Question Provenance, benchmarks stay isolated, and the bank is private by default.
- [Define the Human Benchmark and Audit Contract](issues/06-define-human-benchmark-contract.md): one human confirms roughly thirty agent-prepared Reference Examples once, uncertain cases alone enter the Human Review Queue, and occasional ten-question spot checks hold problematic batches for agent diagnosis without routine per-question approval or statistical machinery.
- [Prototype Creative Proposal Production](issues/07-prototype-creative-proposal-production.md): independent Aspect, Scenario, Perspective, and Contrast scouts create and deduplicate structured Creative Concepts before one composer writes each surviving question; proposal agents never judge admission, see full bank text, or use unapproved taxonomy.
- [Design the Automated Evaluation Topology](issues/08-design-automated-evaluation-topology.md): deterministic preflight and isolated specialist evidence feed separate bank-relation judgments and a rule-based accept/reject/abstain decision; challenges preserve disagreement, retrieval is not a verdict, and uncertainty enters human review.
- [Define Admission Decisions and the Human Review Queue](issues/09-define-admission-and-human-review.md): proposals have only Accept, Reject, or Human review outcomes; acceptance requires complete passing evidence, uncertainty fails closed, human resolutions append rather than erase outcomes, and the same queue resolves uncertain post-accept Theme classification before bank identity exists.
- [Define the Question Bank Record and Lifecycle](issues/10-define-bank-record-and-lifecycle.md): trusted questions start only after final Accept authority and resolved Theme classification, use stable Question IDs with immutable revisions, move through Staged/Active/Retired, keep indexes as projections, and live behind a small authoritative Question Bank module interface.
- [Define Automatic Taxonomy Evolution](issues/11-define-automatic-taxonomy-evolution.md): new Aspects and Perspectives must explain repeated independently created gaps, survive distinctness and shadow-classification challenges, and enter a versioned taxonomy without self-generating support; uncertain cascading changes enter human review.
- [Define Coverage and Bank-Completion Policy](issues/12-define-coverage-and-completion.md): a versioned plan marks meaningful Theme + Level + Aspect + Perspective regions Required/Exploratory/Invalid, requires three distinct scenarios per required region, and declares versioned completion only after healthy horizons and repeated low-yield discovery challenges.
- [Define Bank Versioning, Revalidation, and Release](issues/13-define-versioning-and-release.md): immutable hash-identified snapshots freeze exact revisions and policy versions, change-specific revalidation and release gates protect trust, publication swaps one atomic pointer, and rollback selects a prior snapshot without rewriting history.
- [Define the Question Usage Metrics Collection Contract](issues/14-define-question-usage-metrics.md): append-only presentation/skip/edit/confirmation/round events link exact snapshot and revision identities without storing player text; raw pseudonymous data expires, aggregates remain factual, and no enrichment or retrieval module may read the metrics.
- [Research Reliable Automatic LLM Evaluation](issues/03-research-automatic-llm-evaluation.md): automatic judges require a versioned domain human benchmark, bias and correlated-error measurement, preserved independent judgments, calibrated accept/abstain thresholds, and Human Review Queue routing; agent count and debate topology remain undecided until benchmarked.
- [Research Semantic Repetition and Corpus-Diversity Detection](issues/04-research-semantic-repetition-detection.md): wording, Semantic Scenario, Question Aspect, Question Perspective, and Answer Space must remain separate relations in a calibrated hybrid detector rather than collapsing into one similarity score or cluster.

## Completion

- All fourteen tickets are resolved.
- The consolidated build handoff is [`implementation-specification.md`](implementation-specification.md).
- The explicit agent roster, orchestration graph, context isolation, model assignment, parallelism, and failure behavior are in [`llm-multi-agent-architecture.md`](llm-multi-agent-architecture.md).
- Module seams, trusted records, automatic decisions, human-review limits, taxonomy evolution, coverage completion, release safety, and metric isolation are specified.

## Implementation-time selections

- Select concrete proposal and evaluator models by running the approved topology against the Reference Examples; agent count and model diversity are measured choices, not fixed architecture.
- Set deployment-specific cost, throughput, concurrency, and Human Review Queue alert budgets before autonomous operation.
- Select production persistence and vector-index adapters without changing the specified module interfaces.
- These selections do not reopen the product decisions unless evidence shows a quality or operating-contract failure.

## Out of scope

- Candidate Set sampling, ranking, random retrieval, and diversity behavior during gameplay.
- Any repetition policy across successive Candidate Sets or across a room; those are retrieval decisions.
- Adaptive retrieval or allowing Question Usage Metrics to influence Question Bank contents or selection.
- Usage-metrics dashboards and interpretation beyond defining and collecting the raw facts.
- Locale-specific Question Banks, changes to canonical-English generation, or redesigning Question Translation.
- Adding new player-facing Themes or Levels.
- Implementing or deploying the Question Enrichment Pipeline, generating the full Question Bank, and migrating the live game to bank retrieval.
