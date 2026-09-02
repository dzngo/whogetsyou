# Define Bounded Human Review and Failure Semantics

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Prototype Cascaded Quality Evaluation](04-prototype-cascaded-quality-evaluation.md)

## Question

Which concrete question uncertainties deserve one of the ten available human-review slots, which candidates are automatically rejected when the queue budget is exhausted, and how do model failures, budget exhaustion, partial batches, retries, and resumptions preserve auditability without creating another unbounded backlog?

## Answer

The 200-question production campaign may expose at most ten distinct questions to a human. Six slots are available for residual automated uncertainty and four are protected for release spot-checking. Unused uncertainty slots may increase the spot-check sample; protected spot-check slots may never be consumed by uncertainty. The costed pilot receives its own smaller bound in the pilot contract.

### What deserves review

Only genuine question-specific uncertainty remaining after the configured automated escalation is reviewable:

- quality uncertainty that remains after the selective high-reasoning evaluator;
- semantic-repetition uncertainty that remains after the batched high-reasoning relation judgment;
- field-level metadata uncertainty from an otherwise schema-valid metadata response.

Deterministic or model-definitive rejection is terminal and receives no review. Provider timeouts, malformed or missing batch responses, budget or attempt exhaustion, evaluator drift, pair overflow, unavailable or mismatched embedding artifacts, unexpected model identity, and Unknown Spend are operational outcomes. They create failed-stage records, never Review Packets.

### Review Packet and slot allocation

One distinct question consumes at most one slot. Its versioned Review Packet consolidates the exact immutable question text, Level, provenance, snapshot and relevant neighbour IDs, policy/model/prompt versions, evidence IDs, bounded reason codes, and all known quality, semantic, and metadata uncertainties without private chain-of-thought. Later evidence is appended as an immutable packet supplement; it does not allocate another distinct-question slot or overwrite earlier human resolutions.

Allocate the six uncertainty slots by risk: semantic repetition first, quality second, metadata third, with stable creation order inside a class. If all six slots are allocated, a newly unresolved quality or semantic candidate receives an automatic Reject Admission Outcome with `review_budget_exhausted`. A Staged Question with unresolved metadata remains staged with explicit pending fields; it is not rejected and creates no unbounded backlog entry.

### Human authority

For admission uncertainty, a reviewer may Accept or Reject the exact question text. Human acceptance produces a versioned human Admission Outcome that cites the automatic abstention and Review Packet. Editing never accepts text in place: it creates a new proposal and the exact edit must pass the complete pipeline. For metadata, the reviewer may choose approved Theme, Aspect, or Perspective values, confirm a valid empty Theme set, provide bounded open descriptors, or leave fields pending. Hold keeps the packet unresolved and continues to consume its slot.

Before a release, unresolved admission packets are simply excluded from the candidate snapshot. Review Packet and resolution histories are append-only and idempotent; no human action mutates the evidence or question text it reviewed.

### Failures, partial work, and resumption

There are no automatic provider retries. Every successful stage result, Staged Question, terminal rejection, open Review Packet, invocation envelope, ledger reservation/reconciliation, and failed-stage record is durable. A partial creative or evaluation batch preserves independently completed items; a failed batch does not create human cases for its missing items. Metadata failure leaves already staged questions with pending metadata.

Continuation requires a separately authorized run. It references the prior run, retains unresolved Unknown Spend, obtains fresh Budget Reservations for new attempts, reuses validated application-cache results, and uses stable idempotency keys so it cannot duplicate questions, evidence, rejections, or Review Packets. A resumed run does not reinterpret a prior transport failure as free and does not silently repeat it.

Every run report includes review slots authorized, allocated, open, resolved, and remaining; distinct question IDs; priority and reason codes; automatic rejections caused by queue exhaustion; operational failure counts; and the prior-run identifier for any continuation. This keeps the human workload and the failure backlog independently visible and bounded.
