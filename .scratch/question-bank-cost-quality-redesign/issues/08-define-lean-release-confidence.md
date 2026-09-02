# Define the Lean Release Confidence Gate

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Prototype Cascaded Quality Evaluation](04-prototype-cascaded-quality-evaluation.md), [Prototype the Hybrid Semantic-Repetition Gate](05-prototype-hybrid-repetition-gate.md), [Define Post-Admission Metadata and Observed-Diversity Feedback](06-define-post-admission-metadata-and-feedback.md), [Define Bounded Human Review and Failure Semantics](07-define-bounded-human-review.md)

## Question

What small Reference Example regression, suspicious-neighbour review, integrity checks, metadata requirements, and ten-question human spot check provide enough confidence to publish a bank snapshot without exhaustive whole-bank LLM revalidation?

## Answer

Release is a deterministic, provider-free verification step over stored evidence. It never calls Gemini or GPT. A snapshot may be published only when all of the following gates pass for the exact manifest being released.

### Frozen evaluator regression

- Maintain one frozen twelve-case Reference Example fixture for the current evaluator configuration. Ignore the existing evaluation corpus for this purpose.
- The fixture covers good Shallow questions, good Deep questions, Level failures, emotional-safety failures, semantic repeats, and related-but-distinct pairs.
- Run the fixture once per exact evaluator configuration under the separate calibration budget. Store a signed regression record and reuse it at release time.
- Release requires a passing regression record whose model, prompt, policy, rubric, thresholds, and fixture hashes exactly match the release manifest. Release itself performs no provider call.

### Release-eligible metadata

- Every question must have a resolved Level and resolved Theme Membership. A confidently empty Theme Membership is resolved and valid.
- Aspect, Perspective, Scenario, Answer Space, and Wording Pattern may remain pending. Their incompleteness is visible in the manifest and diversity report but does not by itself block release.

### Human Release Spot Check

- The production campaign may expose at most ten distinct questions to human review across admission uncertainty and release checking.
- The spot-check sample size is `10 - distinct questions already reviewed for admission uncertainty`, with a protected minimum of four questions.
- Half of the sample is selected deterministically from the highest-risk locally distinct neighbour pairs. The other half is a deterministic sample spread across available Levels and creative strategies.
- The sample and selection inputs are recorded in the release manifest so the same snapshot produces the same sample.
- Any sampled quality or semantic-distinctness failure blocks the entire release. Reject the failed question, diagnose the missed failure mode, update the pipeline or policy, rebuild the snapshot, and require a new matching regression record and spot check. Removing only the sampled failure and publishing the remainder is not sufficient.

### Deterministic integrity gates

Release recomputes and verifies:

- snapshot and content hashes;
- exactly one current Question Revision per included question;
- no Retired or Withdrawn question;
- normalized-text uniqueness;
- valid provenance and source permission;
- complete accepted quality and semantic-repetition evidence;
- resolved Level and Theme Membership;
- no open admission Review Packet;
- compatibility of all policy, model, prompt, taxonomy, and artifact versions; and
- Cost Ledger exposure no greater than the explicit authorization.

Any missing, stale, incompatible, or unverifiable item blocks release.

### Whole-bank semantic confidence

- Rebuild the full local lexical-and-embedding scan for the candidate snapshot.
- Reject exact matches and deterministic extreme near-copies.
- Every pair that falls inside the GPT-review zone must have current stored `distinct` evidence produced under the manifest's compatible semantic policy.
- Missing or stale evidence, a stored `repeat` relation, or unresolved semantic uncertainty blocks release.
- This reuses admission evidence and performs no exhaustive whole-bank LLM revalidation.

### Observed anti-collapse gates

Gross diversity collapse is checked from observed metadata without introducing Theme, Level, or Cartesian coverage quotas:

- at least 90% of questions have resolved Aspect, Perspective, Answer Space, and Wording Pattern metadata;
- no single Aspect exceeds 20% of the snapshot;
- no single Perspective exceeds 30%;
- no single Answer Space cluster exceeds 20%; and
- no single Wording Pattern exceeds 25%.

These are release-level anti-collapse limits, not proposal targets or admission quotas. If metadata needed for the report is below 90% resolved, release blocks until metadata is resolved or the snapshot is rebuilt.

### Size and incremental releases

- The initial published snapshot contains at least 200 release-eligible questions. The 20-candidate pilot never publishes.
- Later releases may add incremental deltas, but every release verifies the entire resulting snapshot under the same gates.

### Immutable release manifest and invalidation

The immutable Release Manifest records exact hashes or versions for:

- included Question Revisions and their admission evidence;
- models, prompts, policies, rubric, and taxonomy;
- embedding model artifact and checksum;
- lexical, embedding, and semantic-review thresholds;
- Cost Ledger and authorization;
- frozen Reference Example fixture and matching regression record;
- Release Spot Check sample, reviewers, and results;
- rebuilt semantic index and scan results; and
- metadata-completeness and diversity reports.

A relevant model, prompt, policy, taxonomy, embedding artifact, threshold, rubric, or fixture change invalidates the previous regression and spot-check evidence for a new release. A new matching regression and Release Spot Check are required before publication.
