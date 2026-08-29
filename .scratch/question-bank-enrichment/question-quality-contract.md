# Question Quality Contract

## Scope

This contract governs whether one English question is eligible for admission to the Question Bank. It evaluates the question text itself and its relationship to questions already in the bank.

It does not evaluate simulated answers, Question Translation, Candidate Set composition, runtime sampling, or whether gameplay metrics should influence retrieval.

## Core priority

The Question Bank exists primarily to provide understandable questions with broad variety. A plain question that adds a genuinely different scenario is more valuable than a polished question that repeats an existing one, provided the plain question passes every hard gate.

Variety cannot rescue a confusing, unsafe, unrealistic, or otherwise invalid question.

## Construction and classification order

1. Generate an English question for exactly one Level using a diversity brief, without requiring a Named Theme.
2. Apply the individual-text quality gates in this contract.
3. Compare the question globally with the current Question Bank. Do not limit comparison to a Theme.
4. Apply the bank-relative variety gate using the distinct relations defined by the Diversity Ontology.
5. Assign zero or more equal Theme Memberships after generation and global comparison.

Theme is classification metadata, not an input requirement or quality gate. A question may have several Theme Memberships and has no primary Theme. Random is a wildcard, never a stored Theme Membership.

Question Aspect is global and theme-independent. The current Theme-owned Question Angle remains only a legacy generation aid.

## Hard gates for every question

An admitted question must satisfy all of these rules:

- **Understandable**: one natural English question with one clear answer task.
- **Answerable from ordinary experience**: no specialist knowledge, trivia lookup, inaccessible premise, or hidden prerequisite.
- **Boundedly open**: concrete enough to prompt a short immediate answer while leaving room for different players to answer differently.
- **Realistic**: the player can plausibly answer, choose, remember, or describe what they would do. Generated fantasy, cartoon, object-personification, or contrived absurdity fails unless a later contract explicitly changes the Shallow Humor Boundary.
- **Level-correct**: it obeys exactly one of the Shallow or Deep contracts below.
- **Safe**: no cruelty, discriminatory assumption, sexual pressure, forced embarrassment, private exposure, or emotionally coercive disclosure.
- **Structurally clean**: no compound question, requested explanation plus answer, or wording whose interpretation depends on punctuation tricks.
- **Bank-distinct**: it does not violate the approved wording, Semantic Scenario, Question Aspect, Question Perspective, or Answer Space repetition boundaries.
- **Canonical-only judgment**: admission judges the English bank question. Translation quality is evaluated separately.

A natural forced choice such as "Do you usually text or call?" may pass because it offers meaningful alternatives. A bare yes/no question fails when its answer carries little information.

## Shallow contract

A Shallow question must be lightweight, realistic, low-pressure, and immediately answerable. It may ask a generic poll-style preference and does not need to reveal a distinctive personal characteristic.

Valid Shallow answers can describe an everyday preference, habit, routine, taste, small joy, simple choice, or plausible reaction. Humor is optional. Engagement and playful potential are graded qualities, not hard requirements.

Examples that pass the individual-text gates:

- "What is one kind of place you like spending time in?"
- "When a new cafe opens nearby, what drink do you try first?"
- "When you want a quick update, do you usually text or call?"

Examples that fail:

- "What makes you happy?" — too unbounded to prompt an immediate concrete answer.
- "If your pocket had a tiny plant that needed a daily snack, what would you feed it?" — contrived object-personification rather than a realistic question.
- "Which food would you become, and why would it make you feel confident?" — fantasy, compound, and unnecessarily reflective for Shallow.

## Deep contract

A Deep question must invite a personally characteristic answer: the Storyteller's own value, memory, relationship pattern, belief, regret, hope, aspiration, or self-understanding. Personal revelation is a hard gate, not merely a graded preference.

Deep remains emotionally safe. It may invite reflection or vulnerability, but it must not demand traumatic disclosure, shame, intimate details, or a confession the player may feel pressured to provide.

Examples:

- Pass: "Which value has become more important to you as you've grown?"
- Pass: "What small act from someone else changed how you understand care?"
- Fail: "What is something people value?" — impersonal rather than characteristic of the Storyteller.
- Fail: "What is the most traumatic thing you have never told your family?" — coercive and unsafe.

## Bank-relative variety

Variety is evaluated across the whole bank before Theme Membership is assigned. Exact wording alone is insufficient: the comparison must preserve separate judgments for Wording Pattern, Semantic Scenario, Question Aspect, Question Perspective, and Answer Space.

The precise definitions and relation boundaries are recorded in [`diversity-ontology.md`](diversity-ontology.md). Exact calibrated thresholds and admission consequences remain downstream decisions.

## Graded qualities

After every hard gate passes, evaluators may grade:

- naturalness and economy of wording;
- immediate engagement or playful potential;
- execution of Bounded Openness;
- usefulness of the question's contribution to bank variety;
- for Deep, strength and safety of the invitation to personal reflection.

Humor is not a standalone criterion. The existing `Not funny` review tag is not an admission failure and should be retired when the review harness is aligned with this contract.

Numerical thresholds, reviewer labels, calibration evidence, and the boundary between automatic acceptance and abstention belong to **Define the Human Benchmark and Audit Contract** and **Define Admission Decisions and the Human Review Queue**.
