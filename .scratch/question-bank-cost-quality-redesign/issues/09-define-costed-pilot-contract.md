# Define the 20-Candidate Costed Pilot Contract

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Define the Enrichment Budget and Cost Ledger](02-define-enrichment-budget-contract.md), [Prototype the Lean Creative Batch](03-prototype-lean-creative-batch.md), [Prototype Cascaded Quality Evaluation](04-prototype-cascaded-quality-evaluation.md), [Prototype the Hybrid Semantic-Repetition Gate](05-prototype-hybrid-repetition-gate.md), [Define Post-Admission Metadata and Observed-Diversity Feedback](06-define-post-admission-metadata-and-feedback.md), [Define Bounded Human Review and Failure Semantics](07-define-bounded-human-review.md), [Define the Lean Release Confidence Gate](08-define-lean-release-confidence.md)

## Question

What exact inputs, $0.20 stop condition, output counts, accepted-yield threshold, human-review maximum, repetition inspection, quality spot check, cost report, and scale-or-redesign decision make the first 20-candidate live pilot safe and informative?

## Answer

The pilot is one separately authorized, non-publishing Enrichment Run that proposes exactly twenty new questions and exercises the complete redesigned path. It validates model behavior and unit economics; it does not authorize the `$2` production campaign.

### Inputs and candidate composition

- Generate ten Shallow and ten Deep Question Proposals.
- Use four isolated Gemini Flash high-thinking creative calls, five question texts per call, with one approved creative strategy assigned to each call.
- Assign two calls to each Level. Later batches rotate the Level-to-strategy pairing instead of treating the pilot's pairing as a permanent matrix.
- Supply the requested Level, Question Quality Floor, strategy mission, bounded output schema, pinned prompt/model/policy versions, and compact trusted-bank avoidance summary.
- Supply no target Theme, Coverage Region, taxonomy completion target, sibling output, or legacy 248-case review backlog.
- Compare proposals with the current trusted Question Bank Snapshot, if one exists, but do not import unresolved legacy review cases as evidence.

### Hard budget and attempt stop

The pilot authorizes at most `$0.20` of worst-case list-price exposure and twelve actual provider attempts. The planned maximum stage reservations are:

| Stage | Maximum reservation |
|---|---:|
| Four creative calls | `$0.097200` |
| Ordinary quality evaluation plus one uncertainty escalation | `$0.068250` |
| One ambiguous-pair semantic call | `$0.020250` |
| One metadata batch | `$0.014175` |
| **Total** | **`$0.199875`** |

Before every call, the shared Cost Ledger must atomically reserve the call's complete worst-case exposure while protecting the remaining downstream allowance. The run stops before a call that cannot fit either the remaining dollar authorization or attempt limit. It never retries automatically, changes model silently, weakens a gate, samples away unresolved pairs, or spends the final `$0.000125` margin.

### Complete candidate accounting

Every proposed question ends the pilot in exactly one durable state:

- Staged Question;
- Rejected Question Proposal;
- Awaiting Human Review; or
- Operationally Unresolved.

No candidate may disappear from the report. Independently completed items from a partial batch remain valid evidence. Missing, malformed, or operationally failed items do not count as accepted.

### Scale-validation thresholds

The pilot passes its yield and variety gate only when all of these conditions hold:

- at least fourteen of twenty proposals become Staged Questions;
- at least six accepted questions come from each Level;
- each of the four creative strategies contributes at least two accepted questions;
- total pilot exposure divided by the number of accepted questions is no more than `$0.01`;
- every Staged Question has resolved Theme Membership, including a confidently empty set when appropriate; and
- at least 90% of Staged Questions have resolved Aspect, Perspective, Answer Space, and Wording Pattern metadata.

The per-accepted-question limit is the direct unit-economics evidence that two hundred accepted questions can fit within the `$2` production authorization. The count and distribution thresholds prevent a cheap result from hiding severe rejection or strategy collapse.

### Human work and spot checking

At most five distinct pilot questions may be exposed to a human:

- one slot for residual automated admission uncertainty; and
- four protected pilot spot-check questions.

The uncertainty slot follows the same Review Packet, authority, and no-edit-in-place rules as production. Additional uncertain candidates are not silently accepted and do not create more human work; they fail the pilot's low-human-operability requirement.

Select the four protected spot-check questions deterministically from the candidates forming the two highest-risk locally distinct semantic pairs. If those pairs contain fewer than four distinct candidates, fill the remaining positions across available Levels and creative strategies using the pinned deterministic sampler. Reviewers assess each selected question against the complete Question Quality Floor and inspect the suspicious pair relationships and nearest trusted-bank neighbours.

The pilot requires zero human-discovered quality failures and zero false-distinct semantic repeats. A defect is evidence that the automated pipeline is not ready to scale; it is not repaired only by deleting the sampled question.

### Immutable pilot report

The report records:

- all twenty candidate IDs, exact texts, Levels, strategies, provenance, and terminal states;
- quality, semantic-repetition, metadata, rejection, and Review Packet evidence;
- every provider, role, requested and returned model, prompt/policy version, attempt, cache outcome, failure, and token-usage record;
- authorized, reserved, reconciled, Unknown Spend, remaining exposure, and cost per accepted question;
- accepted yield by Level and strategy;
- semantic pair routing, pair-overflow count, and inspected relationships;
- metadata resolution and observed-diversity distributions;
- human-review selection, decisions, and discovered defects; and
- a pessimistic projection for producing two hundred accepted questions from observed exposure and yield.

The report contains no credentials and is content-addressed with the exact input snapshot and configuration hashes.

### Scale or redesign

The pilot recommends requesting separate production authorization only if every threshold above passes and the run has:

- no Unknown Spend;
- no operational failure;
- no semantic pair overflow;
- no unresolved admission uncertainty beyond the one bounded human slot; and
- no human-discovered quality or repetition defect.

A passing pilot does not start production or spend the `$2`; it only supplies evidence for a separate authorization. Any failed condition produces `redesign_required`. There is no automatic paid rerun, threshold waiver, or partial scale-up.
