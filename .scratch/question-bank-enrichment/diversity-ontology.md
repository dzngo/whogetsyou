# Question Bank Diversity Ontology

## Decision

Question Bank diversity is represented by several explicit facets and pairwise relations. No single similarity score, embedding distance, or cluster is authoritative.

The ontology applies globally across the bank before Theme Membership is assigned.

## Per-question facets

Every classified bank question has:

- exactly one **Level**;
- zero or more equal **Theme Memberships**;
- one **Question Aspect**;
- one **Semantic Scenario**;
- one **Question Perspective**;
- one **Answer Space**;
- one **Wording Pattern**.

Assignments are versioned evidence rather than permanent truths. Later lifecycle and taxonomy tickets define identity, confidence, reclassification, and evolution behavior.

## Canonical facets

### Question Aspect

The theme-independent subject or life facet being explored, such as meetings, unexpected free time, communication channels, or carrying traditions forward.

Question Aspect replaces Theme-owned Question Angle for Question Bank classification. The existing Question Angle Catalog remains a legacy input to the current real-time generator until migration; it is not the bank's diversity ontology.

### Semantic Scenario

The concrete situation, event, or condition posed by the question after wording is normalized.

Examples:

- an unplanned free hour appears;
- a meeting becomes chaotic;
- requesting a quick update;
- choosing a childhood tradition for future family life.

### Question Perspective

The lens applied to the subject, such as preference, habitual reaction, memory, aversion, trade-off, aspiration, self-perception, or social role.

Sharing a Perspective does not itself make two questions repetitive. Useful lenses should recur across unrelated Aspects and Scenarios.

### Answer Space

The semantic kind of short answers invited by the question, inferred from the text rather than generated through answer simulation.

Examples include leisure activities, meeting types, communication channels, family traditions, foods, or group roles and behaviors.

Answer Space catches corpus monotony that Scenario or Aspect labels may miss, such as many differently framed questions that all solicit foods.

### Wording Pattern

The linguistic form of the question independently of its meaning, such as a situational `what do you do first` frame or a forced choice.

Wording Pattern supports phrase and structure variety but never stands in for semantic comparison.

## Pairwise relations

Comparison produces separate relation judgments for each facet. Implementations may use `same`, `overlapping`, and `different` where a binary label is too brittle, but they must preserve the facet boundaries.

- **Wording relation**: exact, near-paraphrase, or structurally different.
- **Scenario relation**: same situation, overlapping situation, or different situation.
- **Aspect relation**: same subject, related subject, or different subject.
- **Perspective relation**: same or different lens, with an optional related state when calibrated evidence supports it.
- **Answer-space relation**: substantially the same, overlapping, or different answer kind.

Lexical and embedding similarity may shortlist neighbors. Structured facet assignment and calibrated relation-specific adjudication decide what the overlap means.

## Repetition interpretation

Two questions are strong semantic-repeat candidates when their Semantic Scenario, Question Perspective, and Answer Space substantially coincide, even if wording differs.

Sharing only a Question Aspect is acceptable when Scenario, Perspective, and Answer Space differ. Sharing only a Question Perspective is also acceptable across unrelated content.

Examples:

- `sudden free hour` versus `extra hour to yourself`: strong semantic-repeat candidate because Scenario, Perspective, and Answer Space coincide.
- `meeting that makes you check the clock` versus `role in a chaotic meeting`: shared Aspect only; retain as distinct.
- `quick update: text or call` versus `fast catch-up: call or message`: strong semantic-repeat candidate despite wording variation.
- `drink tried first at a new cafe` versus `item unpacked first at a hotel`: shared Perspective only; retain as distinct.

Exact thresholds, uncertainty behavior, and automatic admission consequences belong to **Define the Human Benchmark and Audit Contract**, **Design the Automated Evaluation Topology**, and **Define Admission Decisions and the Human Review Queue**.

## Multi-Theme behavior

Theme Membership does not own Question Aspect. For example, "Which hobby would you turn into a job if money did not matter?" has one global Aspect and may hold Hobbies, Work, and Goals memberships equally.

This avoids forcing a primary Theme or duplicating an Angle assignment for every Theme Membership. Random remains a wildcard rather than a membership.

## Prototype evidence

The decision was validated through the interactive logic prototype on branch `codex/prototype-question-bank-diversity-ontology`, commit `4a2e01f`, at `prototypes/question_bank_diversity_ontology.html`.
