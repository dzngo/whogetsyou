# Define the Enrichment Budget and Cost Ledger

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Research Provider Cost Accounting Signals](01-research-provider-cost-accounting.md)

## Question

What exact cost, provider-attempt, retry, reservation, reconciliation, unknown-price, cache-reuse, concurrency, interruption, and reporting rules make the $2 production ceiling and $0.20 pilot ceiling hard operating contracts rather than advisory estimates?

## Answer

The `$2` production ceiling and `$0.20` pilot ceiling bound the worst-case USD list-price exposure that this application authorizes. They do not promise an identical provider invoice because provider accounting can be delayed and can include taxes, credits, or unrelated activity. The Question Quality Floor is never weakened to meet either ceiling.

Every actual provider request is an attempt and must have finite input and generated-token bounds. Before sending it, the shared ledger atomically creates a Budget Reservation for its worst-case cost using a versioned price catalog pinned at run start. Unknown, stale, or unreservable model configurations fail closed with `budget_unreservable`. Gemini Flash high-thinking remains the preferred creative model, but it may run only through a native adapter that supplies a defensible reservation and native usage reconciliation; the pipeline neither silently changes models nor relaxes the ceiling.

Successful attempts reconcile their reservations against provider-native usage. Application-cache hits require no provider reservation and record zero incremental spend; provider-side cache discounts are credited only after usage reports them. A timeout, interrupted response, crash with an unreconciled active reservation, unexpected model identity, or transport-ambiguous failure moves the entire reservation to Unknown Spend. Such attempts are not retried automatically. A later attempt is allowed only when the remaining budget can cover both retained Unknown Spend and the fresh reservation.

All workers share the same transactional ledger and reserve atomically before concurrent calls. The scheduler protects a planned downstream allowance for evaluating and classifying already-created candidates, rather than allowing creative work to consume the whole run. Initial guardrails are at most 12 actual provider attempts in the pilot and 100 in production; cache hits do not count, while sends, retries, and ambiguous attempts do. A later costed topology may lower these limits but may not raise them without a new explicit contract.

The budget always wins over the question-count target. At exhaustion, completed accepted questions remain staged, the run becomes `budget_exhausted`, and no more calls launch. A separately authorized continuation may consume that immutable state. If the pipeline cannot reach its target inside the ceiling, the topology fails validation and must be redesigned rather than overspending.

Each run report records authorized, reconciled actual, active reserved, unknown, and remaining amounts; provider, role, model, price-catalog version, attempts, cache hits, retries, failures, and token usage; and no credentials. Calibration, reference-example work, and prompt experiments use a separate explicit budget—initially no more than `$0.50`—and cannot consume or inherit unused production allowance.
