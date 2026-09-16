# Question Bank v3 non-paid qualification report

Date: 2026-09-15

All cases below ran through n8n's test executor with provider, trigger,
PostgreSQL, HTTP, and called-subworkflow boundaries pinned for that execution.
Therefore these executions made no paid OpenAI or Gemini calls and made no
database writes. The separate disposable PostgreSQL contract suite exercised
the real database functions and transactions.

| Case | Workflow | Execution | Result |
|---|---|---:|---|
| Insufficient provider budget | Reserve provider budget | 7 | Returned `reserved=false` and `insufficient_budget` |
| Quality rejection | Evaluate Question Bank batch quality | 13 | Applied the independent decision and completed the stage |
| Quality uncertainty | Evaluate Question Bank batch quality | 14 | Invoked escalation exactly once and completed the stage |
| Quality provider failure | Evaluate Question Bank batch quality | 15 | Isolated only the failed group and completed the stage |
| No preflight candidates | Preflight and embed Question Bank batch | 16 | Skipped the loop and completed the stage |
| Exact duplicate | Preflight and embed Question Bank batch | 17 | Completed without invoking the embedding path |
| Embedding failure | Preflight and embed Question Bank batch | 18 | Isolated only the failed candidate and completed the stage |
| No semantic candidates | Judge and admit Question Bank batch | 19 | Skipped the judge and completed the stage |
| Semantic duplicate | Judge and admit Question Bank batch | 20 | Routed the duplicate decision to deterministic application |
| Semantically distinct | Judge and admit Question Bank batch | 21 | Routed the distinct decision to deterministic admission |
| Semantic uncertainty | Judge and admit Question Bank batch | 22 | Routed the uncertain decision to deterministic review admission |
| Semantic provider failure | Judge and admit Question Bank batch | 23 | Isolated only the failed group and completed the stage |
| Structured-output repair | Repair structured agent output | 24 | Returned the repaired object and repair invocation ID |
| Cancellation before worker start | Continue Question Bank campaign | 25 | Started no batch and returned durable cancelled status |
| Confirmed Gemini 503 | Invoke Gemini agent attempt | 26 | Released the reservation and returned the explicit retry signal |
| Ambiguous provider result | Invoke Gemini agent attempt | 27 | Routed to `unknown_spend` instead of retrying |
| Four-mission generation fan-out | Generate Question Bank batch candidates | 28 | Invoked Creative exactly four times, once per mission, then returned the persisted count |
| Full batch orchestration | Process one Question Bank batch | 29 | Executed generation, quality, preflight, semantic, metadata, and completion exactly in order |
| Accepted-question CSV export | Export Question Bank | 30 | Produced a two-row `text/csv` file with the expected filename |
| Read-only campaign status | Control Question Bank campaign | 31 | Returned status without launching a worker |
| Cooperative cancellation command | Control Question Bank campaign | 32 | Returned the persisted cancel request without launching a worker |
| Authorized resume command | Control Question Bank campaign | 33 | Launched one new worker only on the resume branch |
| Campaign launch receipt | Run Question Bank campaign | 34 | Persisted/froze first, launched the worker second, and returned the campaign ID |
| OpenAI repair recursion guard | Invoke OpenAI agent attempt | 2822 | A malformed repair-agent response was logged, then stopped as unresolved without recursively invoking Repair |
| Gemini repair recursion guard | Invoke Gemini agent attempt | 2823 | A malformed repair-agent response was logged, then stopped as unresolved without recursively invoking Repair |

The tests discovered and fixed a zero-row n8n behavior: a node that returns no
items does not execute downstream completion nodes. The quality, preflight,
semantic, and campaign-token queries now return an explicit sentinel item and
an adjacent IF node skips paid or iterative work while still returning the
durable stage/campaign result.

The extended zero-row audit also changed each failure-isolation query to return
an aggregate `marked_count`. This guarantees its loop-back still executes if a
concurrent state change leaves zero candidates to update.

After the path matrix passed, the shared Error Trigger workflow was published
as active version `2cab8e09-07e8-4126-b5ff-23d9d945770f`. A read-back audit
confirmed that all 37 other Question Bank v3 workflows reference it through
their `errorWorkflow` setting.

The pinned execution viewer does not visually label pinned nodes. The pin data
is scoped to each test execution and is not saved on the workflow canvas.
For executions 2822 and 2823, the trigger, provider response, reservation,
reconciliation, and schema-failure persistence nodes were pinned. No provider
API call or database mutation occurred.

Executions `2844` and `2845` pinned the repair trigger, prompt loader, provider,
and persistence boundaries. They prove respectively that a repaired payload is
accepted only after original-schema validation and that an invalid repaired
payload is persisted as `schema_failed`. A repair payload whose `decision` violated the original role enum was
rejected as `operationally_unresolved` with
`structured_output_repair_schema_mismatch`. Execution `2842` pinned the
semantic-stage trigger, database reads, Semantic Judge result, and admission
write. With `nearest_questions: []`, the first empty-bank candidate still
traversed `6. Semantic Judge` before admission. Both were no-cost manual
executions; n8n does not retain a visual pin marker in its execution viewer.

Executions `2847` and `2848` pinned the provider-attempt trigger and reservation
result. A previously traced Gemini 503 returned `unavailable_503`, and a traced
OpenAI HTTP failure returned `retryable_failure`, without executing either paid
provider. Execution `2850` pinned Observation and Mission Writer output and
rejected duplicate mission slots with the wrong level mix before Creative
fan-out. Execution `2851` pinned a two-candidate quality group with only one
decision; the complete group followed the isolation branch and the apply node
did not execute. All were no-cost manual executions.

Executions `2852` through `2856` exercise the hardened embedding subworkflow.
They prove cached success, newly stored success, a definite HTTP 503 failure,
budget denial, and cached failure respectively. The trigger, budget/reconcile/
release subworkflows, OpenAI HTTP request, and both PostgreSQL nodes were pinned;
only the deterministic IF and Edit Fields routing executed. No provider request,
database mutation, or charge occurred. The published embedding workflow now
returns explicit results on every reservation branch and persists compact
success/failure traces without storing a second copy of the 1536-number vector.

Executions `2857` through `2859` qualify the final reliability hardening. In
`2857`, the metadata agent returned only one of two required candidate IDs; the
workflow returned `metadata_deferred`, and the pinned apply node did not run.
In `2858`, all four loop iterations persisted a mission before entering the
Creative node, then completed the generation stage. In `2859`, the Semantic
Judge processed a candidate carrying its durable candidate ID and completed
admission. Every database and called-subworkflow boundary was pinned, so these
executions made no provider requests, database mutations, or charges.

Executions `2860` and `2861` close the resume-contract qualification. The
Gemini attempt returned a flattened cached success, while the OpenAI attempt
returned an active-lease `in_flight` result. In both cases the cached branch
completed and the pinned paid provider node did not execute. The SQL contract
suite separately proves that an active 30-minute lease preserves the original
reservation and that only an explicitly expired lease transitions to
`unknown_spend`.

Executions `2862` and `2863` qualify the final duplicate-worker stop for Gemini
and OpenAI attempts. Each trigger and reservation result was pinned with an
active-lease `in_flight` outcome. The new Filter node emitted zero items on its
normal output and became the last executed node; no provider, reconciliation,
persistence, batch-stage, or campaign-completion node ran. Execution `2864`
was superseded because its embedding reservation pin used an obsolete nested
cache shape; the replacement live-boundary execution is recorded below. These
manual tests made no provider request, database mutation, or charge.

Execution `2869` is the replacement embedding qualification. Only the trigger
and paid/downstream safety boundaries were pinned; `Reserve embedding budget`
called the real reserve subworkflow, which returned its flattened
`attempt_in_flight` contract from PostgreSQL. The embedding return shaper
preserved `transport_status=in_flight`, the Filter emitted zero normal-output
items, and the paid embedding node did not execute. The temporary $0.000001
database-only reservation was released immediately afterward, leaving zero
active reservations and no unknown-spend balance.

## Database contract evidence

`./test-sql.sh` passed on 2026-09-15 in disposable PostgreSQL. It covers real
campaign control, budget reservation and reconciliation, in-flight provider
leases, conservative recovery of expired ambiguous attempts, unknown spend, full attempt-identity reuse
guards, exact 50/50 mixed-target validation, mission-level/mix validation,
duplicate quality-decision rejection, mission/candidate persistence, exact duplicate detection, distinct
admission, atomic exact-set metadata assignment, theme assignment, semantic duplicate handling, operationally
unresolved state, vector retrieval, and batch completion. The transaction is
rolled back and the disposable container is removed after the test.
