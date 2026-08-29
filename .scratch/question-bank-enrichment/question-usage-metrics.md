# Question Usage Metrics Collection Contract

## Purpose and Non-Purpose

Question Usage Metrics record how exact Question Bank revisions are encountered during play so future analysis can study appearances, skips, edits, and confirmations.

For this effort they are write-only facts. They do not change Question Bank contents, proposal priorities, evaluation, coverage, admission, release, or gameplay retrieval. Any later adaptive use requires a separate decision, privacy review, validation plan, and versioned integration.

## Common Event Envelope

Every Question Usage Event contains:

```text
event_id
event_type
schema_version
occurred_at
recorded_at
idempotency_key
game_session_id_pseudonym
round_instance_id
round_sequence
storyteller_session_pseudonym
selected_theme
selected_level
question_bank_snapshot_id | null
question_id | null
question_revision_id | null
presentation_id | null
confirmed_question_instance_id | null
room_language
question_origin
```

`question_origin` is one of `bank`, `bank_edited`, `manual`, or `legacy_generated`. Bank identity fields are required for `bank` and `bank_edited`; they are null for questions that never came from the Question Bank.

Selected Theme records the gameplay request. It must not be interpreted as the question's only Theme Membership.

## Events

### `question_presented`

Emit after a client acknowledges that a question became visible to the Storyteller.

Additional fields:

```text
presentation_id
candidate_position | null
presentation_sequence_in_round
retrieval_policy_version | null
translation_version | null
```

Showing the same Question Revision again creates a new presentation with a new Presentation ID. Transport retries reuse the same idempotency key and do not create another event.

### `question_skipped`

Emit when the Storyteller asks for another question or leaves a presented candidate without confirming it.

Additional fields:

```text
presentation_id
skip_reason: next_question | previous_question | theme_changed | level_changed | manual_entry | round_abandoned | other_system
```

A skip must reference an earlier presentation in the same round. Do not infer a skip merely from a missing confirmation; disconnections and unfinished rounds remain distinguishable.

### `question_edit_completed`

Emit once when an editing session ends through confirmation, replacement, or abandonment. Do not emit keystrokes.

Additional fields:

```text
presentation_id | null
edit_outcome: confirmed | replaced | abandoned
edit_size_bucket: tiny | small | substantial
original_character_count | null
edited_character_count
```

When editing began from a bank question, retain its exact bank identity in the common envelope. Do not store the raw edited text, a reusable text fingerprint, or edit diff in the metrics store.

### `question_confirmed`

Emit exactly once when the round leaves question selection with a final Confirmed Question.

Additional fields:

```text
confirmed_question_instance_id
presentation_id | null
confirmation_origin: bank_unchanged | bank_edited | manual | legacy_generated
was_edited
```

If a bank question was edited, the event retains the original Question ID and Revision ID for usage attribution, but the edited text does not become a Question Revision and does not change the Question Bank.

### `question_round_finished`

Emit when the round using the Confirmed Question completes or is abandoned. This supports denominator checks without collecting answer content.

Additional fields:

```text
confirmed_question_instance_id
round_outcome: completed | abandoned
```

This event records only lifecycle completion. Scores, answers, guesses, and Game Statistics remain outside Question Usage Metrics.

## Event Invariants

- Events are append-only and deduplicated by idempotency key.
- Server receipt time is recorded separately from client occurrence time.
- A Presentation ID belongs to exactly one round and one visible question origin.
- A bank presentation always carries snapshot, Question ID, and Question Revision ID together.
- A confirmation references either one earlier presentation or an explicit non-bank origin.
- At most one `question_confirmed` exists per Round Instance ID.
- `bank_unchanged` confirmation must reference the exact presented Question Revision.
- `bank_edited` confirmation must be preceded by an edit-completed event or carry a recoverable missing-event error flag outside the trusted aggregate.
- Invalid or incomplete events go to telemetry repair storage and do not silently enter trusted aggregates.

## Privacy Boundaries

Do not collect in this event stream:

- player or room names;
- account identifiers, email addresses, or stable cross-game player IDs;
- IP addresses or device fingerprints;
- raw Canonical, Display, manual, or edited question text;
- Storyteller Answers, Suggested Answers, listener guesses, scores, or chat;
- free-form skip or edit explanations.

Game and Storyteller pseudonyms are random per game session and cannot be used to build cross-game profiles. Access to raw events is restricted to operational and approved analysis roles, and access is audited.

## Retention

- Keep raw pseudonymous Question Usage Events for 90 days to validate event sequences and repair aggregation defects.
- After 90 days, delete raw events and retain only aggregate counts grouped by Question Revision, Question Bank Snapshot, selected Theme, selected Level, event type, and time period.
- Aggregates contain no room, player, presentation, or confirmed-question-instance identifiers and may be retained with Question Bank history for future longitudinal comparison.
- A shorter legal, consent, or product privacy requirement overrides these defaults.

## Aggregate Facts

The write pipeline may derive factual counts such as presentations, skips, unchanged confirmations, edited confirmations, manual replacements, and completed rounds per exact Question Revision and snapshot. Do not compute a quality score, retirement recommendation, coverage priority, or retrieval weight in this effort.

## Architectural Isolation

```text
gameplay events -> usage event sink -> validated aggregate store

Question Bank / Proposal / Evaluation / Coverage / Retrieval  -X->  usage store
```

- Gameplay writes events through a narrow append interface.
- The Question Bank stores no mutable usage counters.
- Enrichment briefs, evaluator context, admission rules, taxonomy evidence, and Coverage Plans cannot query usage storage.
- Question Bank releases do not wait for metrics aggregation.
- A future use must add an explicit, versioned read interface after a separate design decision; none exists now.

## Failure Behavior

Metric delivery must never block question confirmation or round progress. Use an outbox or buffered delivery with idempotent retry. If events are lost or invalid, record observability about the loss without inventing usage facts. Bank trust and gameplay correctness do not depend on metric completeness.

## Consequences

- Future analysis can attribute behavior to exact immutable bank content.
- Player-created text and personal game answers stay outside the analytics stream.
- Raw linkable events age out while useful corpus-level counts remain.
- The current autonomous enrichment system cannot create a feedback loop from gameplay popularity.
