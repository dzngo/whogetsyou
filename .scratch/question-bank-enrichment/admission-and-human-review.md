# Admission Decisions and Human Review

## Decision Outcomes

Every completed evaluation produces exactly one Admission Outcome:

1. **Accept**: the proposal may become a Question Bank entry.
2. **Reject**: the proposal does not enter the Question Bank.
3. **Human review**: the automatic system abstains and places the proposal in the Human Review Queue.

There is no separate quarantine outcome. A proposal awaiting a person is already isolated in the Human Review Queue and is never visible to Question Bank consumers.

An automatic Human review outcome is never rewritten. When a person resolves the case, the system appends a human Accept or Reject Admission Outcome that references the automatic outcome, complete Evaluation Evidence, and immutable human resolution. This later outcome supplies final admission authority while preserving the automation's original abstention.

## Automatic Acceptance

A proposal is accepted only when all of the following are true:

- deterministic preflight passes;
- every required specialist judgment exists;
- every hard quality, Level, safety, realism, and structure gate passes;
- Question Aspect, Semantic Scenario, Question Perspective, Answer Space, and Wording Pattern are assigned without material uncertainty;
- the whole-bank neighbor search completed against the intended bank snapshot;
- facet-specific comparisons find no prohibited semantic repeat;
- the evidence challenge finds no unresolved contradiction or new failure pattern;
- every evaluator, rubric, taxonomy, prompt, model, and index version is recorded.

Acceptance is a rule evaluation, not a vote. Theme Membership is assigned afterward as zero-to-many equal memberships; it cannot rescue or disqualify an otherwise evaluated question.

## Automatic Rejection

Reject when the evidence clearly establishes any critical failure, including:

- missing or forbidden Question Provenance;
- unknown or incompatible source permission;
- unsafe or harmful framing;
- text that is not one understandable canonical-English question;
- ordinary answerability or Bounded Openness failure;
- incorrect or indeterminate Level when the evidence clearly supports another outcome;
- Deep text that does not invite characteristic personal revelation;
- unrealistic or structurally broken wording;
- a prohibited semantic repeat in the active Question Bank;
- use of an unapproved taxonomy term as if it were approved.

Record one or more stable reason codes and concise evidence. Rejection is not a request for agents to paraphrase the same failed proposal repeatedly. The proposal factory should normally explore a new Creative Concept.

## Human Review Queue

Send a proposal to human review when the system cannot safely produce either clear acceptance or clear rejection. Examples are:

- any required critical verdict is `uncertain`;
- independent judgments materially conflict;
- an ontology assignment is unstable across plausible readings;
- the semantic-repeat result remains uncertain after the relation check;
- a required evaluation stage still fails after one execution retry;
- the challenge identifies a case outside the current rubric or Reference Examples;
- a likely taxonomy change is needed before the question can be classified.

Human review is not triggered merely because a question is unusual or highly creative. Novelty with complete passing evidence remains eligible for automatic acceptance.

## Reviewer Packet

Show the reviewer only decision-relevant evidence:

- the proposed question and intended Level;
- Question Provenance and source-permission status;
- proposed Aspect, Scenario, Perspective, Answer Space, and Wording Pattern;
- every specialist verdict, reason code, and concise evidence;
- the closest bank neighbors and separate relation judgments;
- the conflict or uncertainty that caused abstention;
- the relevant rubric, taxonomy, bank snapshot, prompt, and model versions;
- execution failures and retry count, if any.

Do not show private chain-of-thought or imply that model vote count is confidence.

## Human Outcomes

A reviewer may:

1. **Accept as-is**, creating an immutable human resolution plus a human Accept Admission Outcome that allows the proposal to enter the normal bank-record creation path.
2. **Reject**, recording a reason code and optional concise note.
3. **Edit**, which creates a new proposal version with the human edit in its Question Provenance and sends it through the full automated evaluation again.
4. **Hold for taxonomy or rubric repair**, linking the proposal to the discovered issue. It remains outside the bank until the issue is resolved and the proposal is re-evaluated.

The human outcome does not silently rewrite the original Evaluation Evidence. The original proposal, evidence, and resolution remain auditable.

## Theme Classification Cases

An automatically accepted question whose later Theme Membership classifier is uncertain enters the same Human Review Queue with case type `theme_classification`. Its reviewer packet contains the question, Level, proposed zero-to-many Named Theme memberships, each classifier's concise evidence, and the current Theme definitions. The reviewer resolves the memberships, including a confident empty set, or edits the question into a new fully evaluated proposal. Only a resolved classification may enter the Question Bank module.

## Retry and Failure Rules

- A failed model or infrastructure stage may retry once with the same input and versioned contract.
- If it still fails, preserve the failure and send the proposal to human review.
- Do not automatically rewrite rejected questions. Generate a different Creative Concept instead.
- A human-edited question is a new proposal version and receives the full evaluation, including global neighbor comparison.
- Missing evidence, unavailable indexes, unknown versions, or storage failures can never default to acceptance.
- A decision write must be atomic: either the full outcome and its evidence references are recorded, or no admission occurs.

## Batch Effects

A clear per-question failure rejects only that proposal. If a reviewer or spot check reveals a repeated evaluator defect, hold the affected enrichment batch, repair the rule or evaluator, and re-evaluate the affected scope before release. This preserves minimal routine human work without allowing a systematic error to spread.

## Consequences

- The Human Review Queue contains genuine uncertainty rather than routine approvals.
- Rejection does not consume repeated agent effort on cosmetic rewrites.
- Human edits remain traceable and cannot bypass automatic safety and distinctness checks.
- Failures are visible and recoverable, never silently converted into trusted bank content.
