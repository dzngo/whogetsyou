# Question Bank Record and Lifecycle

## Identity

A Question Bank entry begins only after final admission authority is Accept, either from automatic evaluation or from a later human Accept outcome that resolves an automatic Human review outcome. Rejected proposals and unresolved Human Review Queue items remain proposal records and never acquire trusted bank identity.

Each entry has two identities:

- **Question ID** is stable for the continuing semantic identity of one bank question.
- **Question Revision ID** identifies one immutable version of that question's text and classifications.

Canonical text is content, not identity. A normalized-text fingerprint supports exact-duplicate detection but must not be used as a Question ID.

## Revision Rule

Never update a trusted revision in place.

- A typo, wording correction that preserves intent, Theme Membership correction, or taxonomy reclassification creates a new revision under the same Question ID.
- A change to the Level, core Semantic Scenario, Question Perspective, or intended Answer Space creates a new proposal and, if accepted, a new Question ID. Retire the old entry if it should no longer be used.
- Any text edit must pass the required evaluation again before it can become the current revision.
- Previous revisions remain readable for audit and old-snapshot reproducibility.

## Trusted Record

One immutable Question Revision contains:

```text
question_id
revision_id
revision_number
previous_revision_id | null
canonical_question
level
theme_membership_ids[]
theme_classification_decision_id
question_aspect_id
semantic_scenario
question_perspective_id
answer_space
wording_pattern
question_provenance_id
evaluation_evidence_id
admission_decision_id
taxonomy_version
created_at
created_by
```

Invariants:

- `canonical_question` is one English question;
- `level` is exactly Shallow or Deep and cannot change within a Question ID;
- `theme_membership_ids` contains zero or more equal Named Themes and never Random;
- `theme_classification_decision_id` proves that the memberships, including a confident empty set, are resolved rather than missing;
- exactly one approved Question Aspect and one approved Question Perspective are referenced;
- Question Provenance and Evaluation Evidence are immutable references to complete records;
- the admitted revision is the exact content covered by the admission decision;
- revision numbers increase monotonically within a Question ID;
- only one revision of a Question ID may be current in a given Question Bank Snapshot.

Semantic fingerprints, vector embeddings, lexical tokens, neighbor caches, coverage counters, and usage totals are derived projections. They may be rebuilt and do not belong to the canonical trusted record.

## Lifecycle

A trusted Question ID has three lifecycle states:

1. **Staged**: accepted and recorded, but not yet included in a released Question Bank Snapshot.
2. **Active**: its current revision is included in the current released snapshot.
3. **Retired**: excluded from future snapshots with an immutable reason, timestamp, and actor.

Rejected and Human review are Admission Outcomes for proposals, not lifecycle states for trusted questions. Supersession is a relationship between revisions, not a fourth question lifecycle state.

Allowed transitions:

```text
accepted proposal -> Staged -> Active -> Retired
                         |        |
                         +-> new accepted revision
```

- Release moves selected staged revisions into a new snapshot and makes their Question IDs Active.
- A correction creates a staged revision. The currently released revision remains active until a later snapshot selects the correction.
- Retirement is append-only and affects future snapshots. Previously released snapshots remain reproducible.
- Reactivation requires a newly evaluated revision and a new release; it never deletes the retirement record.

## Theme Membership Timing

Proposal production does not use Theme. After global evaluation accepts the question, a classifier assigns zero-to-many Theme Memberships against the current Named Themes. A confident result may be an empty set, and Random never becomes a stored membership. An uncertain result creates a classification review case and cannot yet become a trusted Question Revision. Theme classification does not rewrite the Admission Outcome, but it must resolve before the Question Bank module may create the Staged revision.

## Corrections and Retirement

- **Text correction**: create a new proposal revision, retain ancestry in Question Provenance, run complete quality and global-distinctness evaluation, then stage the accepted revision.
- **Metadata correction**: create a new immutable revision and run the checks affected by that field. The release policy determines the exact revalidation scope.
- **Taxonomy merge or deprecation**: create metadata revisions or a versioned projection through the taxonomy-evolution process; never silently rewrite historical revisions.
- **Retirement**: record a stable reason code such as safety change, semantic repeat, source-rights change, quality regression, or taxonomy invalidation.
- **Removal required by law or consent**: restrict the content through a separate compliance process while retaining the minimum non-content tombstone needed to prevent accidental reintroduction. Routine cleanup never hard-deletes history.

## Module Seams

The authoritative module interfaces are consolidated in [Automated Question Bank — Implementation Specification](implementation-specification.md#modules-and-interfaces). The important seams are Proposal Production, Proposal Evaluation, Question Bank Neighbor Index, Human Review, Taxonomy Registry, Coverage Planning, Question Bank, Release, Pipeline Orchestration, and the isolated Question Usage Sink.

Only the Question Bank Module creates Question IDs or changes trusted lifecycle. It rejects any admission package that lacks final Accept authority, complete evidence references, a resolved Theme classification, approved taxonomy references, or provenance. The Proposal Evaluation Module reads a fixed snapshot but cannot mutate it. The Question Bank Neighbor Index Module hides rebuildable lexical/vector projections and returns evidence candidates rather than verdicts. Callers never coordinate storage tables, indexes, and lifecycle events themselves.

## Atomicity and Idempotency

- Every proposal, evaluation run, human resolution, admission, revision, retirement, and release command has an idempotency key.
- Admitting the same accepted package twice returns the original result rather than creating duplicate Question IDs.
- Writing the trusted revision, lifecycle event, and outbox notification is one atomic operation.
- Derived index updates consume the outbox and may retry; an index failure cannot create a partially trusted revision.

## Testing Surface

Test behavior through each module's interface. For the Question Bank module, use a local-substitutable database or in-memory storage adapter behind the module, then assert stable identity, immutable revision behavior, invalid transition rejection, idempotent admission, snapshot reproducibility, and atomic failure behavior. Do not expose internal storage repositories solely for tests.

## Consequences

- Trusted bank records cannot be confused with proposals or review cases.
- A text edit cannot silently inherit evidence for older text.
- Search and coverage projections can evolve without rewriting canonical records.
- Callers learn a small interface while the Question Bank module keeps storage and lifecycle complexity local.
