# Question Bank v3 paid qualification report

Date: 2026-09-15

Status: **paid content and repair-path qualification passed; workflow
publication and cutover complete**.

The first campaign, `qb3-300`, spent `$0.419096` but failed manual content
review because several accepted questions formed repetitive same-batch
clusters. Its 27 admissions were removed from the authoritative bank with a
guarded audit migration and preserved in CSV and agent-run history. Those
candidates now require human review.

Two clean follow-up campaigns exercised the strengthened variety prompts and
one-candidate-at-a-time semantic judge:

- `qb3-1897` spent `$0.272115`. Manual review retained five representative
  questions and moved fifteen repetitive siblings to human review.
- `qb3-2434` spent `$0.224650` and admitted thirteen questions before exhausting
  its budget: five Shallow and eight Deep.

The authoritative v3 bank therefore contains 18 qualification questions: eight
Shallow and ten Deep. All accepted questions have metadata. Every saved
candidate in the two follow-up campaigns is accepted, rejected, unresolved, or
awaiting review; none remains `proposed`. The accepted-question export execution
was `2820`, and the `qb3-2434` candidate export execution was `2821`.

## Why the release gate failed

Manual review found repeated same-batch semantic clusters among accepted Deep
questions, including childhood keepsakes, career-success trade-offs, and
emotional-support memories. The former semantic workflow loaded every
candidate's neighbour list before admitting any candidate in that batch.
Consequently, later candidates could not retrieve questions accepted moments
earlier in the same batch.

The qualification also exposed and fixed three recovery defects:

1. An empty bank gives the first candidate zero neighbours. The semantic stage
   still sends that candidate through the Semantic Judge with
   `nearest_questions: []`; no candidate bypasses semantic judgment.
2. One model response changed a character in an opaque candidate UUID. The
   stage now requires one decision per input and restores IDs from ordered
   workflow input before applying decisions.
3. A replay stopped after the embedding stage because completed embeddings
   produced zero output. Preflight now skips stored embeddings and always
   reaches its completion path.

After content review, semantic admission was redesigned to process candidates
one at a time. Each candidate retrieves a fresh top ten immediately before its
LLM judgment, so a same-campaign acceptance is visible to the next candidate.
In `qb3-2434`, all twenty semantic calls judged exactly one candidate; nineteen
had same-campaign accepted neighbours, while the first correctly had none.

Admission now also locks and checks campaign state and per-level quota inside
the database. Batch completion terminalizes surplus proposed candidates. SQL
contract tests cover both rules.

## Structured-output repair qualification

The provider-attempt workflows previously logged malformed structured output
but did not invoke the existing Repair role. Their live drafts now contain a
guarded same-provider repair call and a recursion stop. Source validation and
saved-graph readback pass. Pinned executions `2822` and `2823` prove that a
malformed response from the repair agent terminates as unresolved instead of
recursing.

The operator then authorized an additional `$0.03` for campaign
`qb3-repair-qualification`. Execution `2834` supplied a pinned malformed
original response and ran the Repair subworkflow and Gemini provider call for
real. The repair returned `succeeded` and restored the original contract as
`{"decision":"distinct"}`. The persisted Repair trace points to the preserved
parent `schema_failed` invocation. Resume accepts that child only when its
structured trace includes `original_schema_validated=true`; pinned executions
`2844` and `2845` cover the valid and invalid branches.

An earlier fixture execution reached Gemini but failed trace persistence because
its pinned parent invocation did not exist in PostgreSQL. Its provider attempt
had already reconciled, so the preserved n8n execution was used to backfill the
missing parent and child audit rows. The fixture was corrected before execution
`2834`. Both real repair calls cost `$0.002991` in total; the campaign has zero
reserved and unknown spend, and the sum of reconciled attempt cost exactly
matches `campaigns.spent_usd`. It was finalized as `cancelled_partial` because
it is a repair-only test and admits no questions.

The approved repair allowance was `$0.03`, leaving `$0.027009` unused. Run,
Control, and Export were published only after the final all-workflow validation,
saved-connection, credential, and operator-trigger audit passed. n8n is now the
sole production owner for new Question Bank campaigns.

## Preserved audit exports

- `exports/qb3-300-accepted.csv` — 27 accepted rows plus header.
- `exports/qb3-300-candidates.csv` — all 80 candidate decisions plus header.

These files contain no credentials or private chain-of-thought. The original
27 rows are no longer part of the authoritative bank; their decisions, prompts,
raw provider outputs, and exports remain available for audit.
