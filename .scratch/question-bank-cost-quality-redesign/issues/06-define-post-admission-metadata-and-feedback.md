# Define Post-Admission Metadata and Observed-Diversity Feedback

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Prototype the Lean Creative Batch](03-prototype-lean-creative-batch.md)

## Question

How are Theme Membership, Question Aspect, Question Perspective, Semantic Scenario, Answer Space, and Wording Pattern assigned cheaply after quality admission; which uncertainty may remain pending on a staged question; and how do observed distributions become compact creative feedback without recreating a hypothetical Coverage Plan?

## Answer

A question becomes a Staged Question immediately after its Level, provenance, complete quality evidence, and semantic distinctness pass. Classification metadata is downstream enrichment: it cannot reject the question, weaken its quality status, or become a prerequisite for initial generation.

### One batched metadata pass

After all passing questions in a run are staged, make at most one `gpt-5.4-mini` medium-reasoning call for up to twenty questions. The call has a 4,500-token input cap and reasoning-inclusive `max_output_tokens=2,400`, producing a worst-case list-price Budget Reservation of `$0.014175`. It receives only question IDs and texts, fixed Levels, Named Theme definitions, and the approved Aspect and Perspective definitions from the pinned Taxonomy Version. There is no per-question call, automatic retry, challenger, or taxonomy-authoring path.

For each question it returns:

- zero or more equal Theme Memberships, never a primary Theme and never Random;
- exactly one approved Question Aspect or `pending`;
- exactly one approved Question Perspective or `pending`;
- one short Semantic Scenario descriptor or `pending`;
- one short Answer Space descriptor or `pending`;
- one short Wording Pattern descriptor or `pending`;
- a field-level status and bounded reason codes without private chain-of-thought.

A confidently resolved empty Theme set is valid and distinct from pending Theme classification. The classifier cannot propose a new Theme, Aspect, Perspective, or Taxonomy Candidate during Bootstrap Enrichment.

### Validation, uncertainty, and failure

The deterministic validator requires exactly one record per requested question ID, removes Random, rejects unknown taxonomy IDs, bounds descriptor lengths, and records model/prompt/taxonomy versions. Unknown IDs, omitted records, invalid cardinality, or explicit field uncertainty leave only the affected fields pending. No invalid value is guessed or silently coerced.

Any metadata field may remain pending on a Staged Question. Genuine field-level model uncertainty creates at most one metadata-review case for that question, containing all its unresolved fields; it does not reopen question admission. A malformed, missing, or transport-ambiguous whole response is an operational `metadata_failed` outcome, not twenty human cases. Its reservation follows the Unknown Spend rules where usage is ambiguous, and it is not retried automatically.

If the `$0.014175` reservation cannot fit the remaining Enrichment Budget, skip the request, preserve every question as staged with pending metadata, and stop with `metadata_budget_exhausted`. The pipeline never removes accepted questions or exceeds the `$0.20` pilot ceiling to finish classification.

### Observed diversity without a Coverage Plan

After at least twenty Staged Questions have resolved metadata, compute distributions deterministically from resolved values only. Track counts for Level, Theme Membership, Aspect, Perspective, clustered Semantic Scenario, clustered Answer Space, Wording Pattern, and pending-field rates. Theme distributions are reporting statistics during Bootstrap Enrichment and do not steer creative prompts.

Create Diversity Feedback containing at most eight overrepresented Aspect, Perspective, Scenario, Answer Space, or Wording patterns for the next creative batch to avoid. It contains no target Theme, underrepresented quota, required combination, Coverage Region, hypothetical taxonomy slot, or question text. Before twenty resolved staged questions exist, creativity uses only the four strategy missions and existing-question avoidance.

Diversity Feedback is advisory. It cannot mutate current questions or taxonomy, affect admission, create human review, or require that a later batch fill a gap. Pending metadata is excluded from pattern counts and reported separately. Question Usage Metrics and these distribution statistics remain available for future sampling work but do not currently influence gameplay retrieval.
