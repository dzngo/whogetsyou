# Redesign the Question Bank Pipeline for Cost-Efficient Quality

Label: wayfinder:map
Status: resolved

## Destination

Produce an implementation-ready redesign specification and migration plan for a simpler Question Enrichment Pipeline that can build 200 accepted staged questions within a hard $2 production budget while preserving the Question Quality Floor and requiring no more than ten human question reviews.

## Notes

- Domain: Question Bank enrichment for "Who Gets You?"; use the canonical language in [`CONTEXT.md`](../../CONTEXT.md).
- This map supersedes the operating topology—not the question-quality decisions—of [`Design the Automated High-Quality Question Bank`](../question-bank-enrichment/map.md).
- Preserve clarity, answerability, emotional safety, Level correctness, characteristic revelation for Deep, and global semantic non-repetition.
- Gemini Flash high-thinking remains the creative model. GPT evaluates; expensive high reasoning is reserved for uncertainty or ambiguous semantic repetition.
- Bootstrap Enrichment generates and evaluates concrete questions before deriving coverage guidance. Coverage Regions and exhaustive taxonomy matrices are not bootstrap gates.
- Production is bounded by both cost and provider-attempt limits. Retries consume budget and the pipeline stops before sending a call that cannot fit.
- The first live validation is one 20-candidate pilot under $0.20. No task on this map may run that pilot without separate explicit authorization.
- Use `grilling` and `domain-modeling` for decision tickets, `prototype` for concrete pipeline behavior, `research` for provider facts, and `codebase-design` for module interfaces.
- This map plans the redesign. It does not refactor the system, resolve the 248 legacy coverage cases, or generate the 200-question bank.

## Decisions so far

<!-- Resolved child tickets are indexed here by name with a one-line gist and link. -->

- [Research Provider Cost Accounting Signals](issues/01-research-provider-cost-accounting.md): successful native responses support list-price reconciliation, while hard run budgets require atomic worst-case reservations, native Gemini usage accounting, mandatory output caps, and retained unknown spend after ambiguous failures.
- [Define the Enrichment Budget and Cost Ledger](issues/02-define-enrichment-budget-contract.md): each provider attempt atomically reserves worst-case list-price exposure, ambiguous outcomes retain Unknown Spend, and budget exhaustion safely stops the run without weakening quality or silently switching models.
- [Prototype the Lean Creative Batch](issues/03-prototype-lean-creative-batch.md): Bootstrap Enrichment uses four isolated Gemini strategy calls returning five question texts each, eliminating concept scouts and per-question Composer fan-out while preserving strategy-level variety.
- [Prototype Cascaded Quality Evaluation](issues/04-prototype-cascaded-quality-evaluation.md): deterministic preflight and two ordinary GPT batches handle routine quality, while one isolated high-reasoning batch is reserved only for uncertainty and never replaces the separate semantic-repetition gate.
- [Prototype the Hybrid Semantic-Repetition Gate](issues/05-prototype-hybrid-repetition-gate.md): a full local lexical-plus-embedding scan resolves only identity, extreme near-copies, and validated all-signal distance; one bounded high-reasoning GPT call preserves separate semantic relations for the ambiguous middle.
- [Define Post-Admission Metadata and Observed-Diversity Feedback](issues/06-define-post-admission-metadata-and-feedback.md): one bounded GPT batch classifies staged questions without admission authority, while deterministic observed distributions yield only a compact avoid-list for later creativity.
- [Define Bounded Human Review and Failure Semantics](issues/07-define-bounded-human-review.md): at most six residual-uncertainty packets and four protected spot-check questions consume the ten-question human ceiling, while operational failures remain durable resumable run state rather than review work.
- [Define the Lean Release Confidence Gate](issues/08-define-lean-release-confidence.md): provider-free release verification combines a frozen evaluator regression, full local semantic rescan with stored ambiguous-pair evidence, deterministic integrity and anti-collapse gates, and a protected human spot check within the ten-question campaign ceiling.
- [Define the 20-Candidate Costed Pilot Contract](issues/09-define-costed-pilot-contract.md): one separately authorized 10-Shallow/10-Deep pilot must fit `$0.20`, stage at least fourteen questions at no more than one cent of exposure each, pass zero-defect quality and repetition checks within five human questions, and satisfy every operational gate before production may be requested.
- [Define Migration from the Existing Enrichment System](issues/10-define-redesign-migration.md): preserve the entire failed bootstrap as a hashed read-only archive, start a clean version-2 store, replace Coverage Plan and fan-out runtime paths with one deep `EnrichmentEngine`, and cut over only after offline verification with non-destructive rollback.
- [Approve the Simplified Question Enrichment Specification](issues/11-approve-simplified-specification.md): the user approved the traced version-2 contract after the integrated state-model prototype demonstrated hard-budget, no-retry, review, semantic-overflow, pilot, and provider-free release behavior.

## Implementation handoff

- The approved source of truth is [`implementation-specification.md`](implementation-specification.md).
- Implement and verify the complete offline version-2 system before any calibration or live pilot call.
- A live pilot requires separate explicit `$0.20` authorization. A production run requires a passing pilot and separate explicit `$2` authorization.
- Any later mature-bank Coverage Plan is a separate future decision; it is not a bootstrap dependency or hidden requirement.

## Out of scope

- Resolving or reusing the 248 Coverage Region review cases from the failed bootstrap.
- Candidate Set sampling, ranking, and adaptive retrieval during gameplay.
- Generating the 200-question bank or spending production API budget while this map is open.
- Automatic taxonomy evolution during the initial 200-question Bootstrap Enrichment.
- Locale-specific banks and Question Translation changes.
