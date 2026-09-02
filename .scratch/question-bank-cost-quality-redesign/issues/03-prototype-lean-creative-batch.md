# Prototype the Lean Creative Batch

Type: prototype
Label: wayfinder:prototype
Status: resolved
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Define the Enrichment Budget and Cost Ledger](02-define-enrichment-budget-contract.md)

## Question

What smallest Gemini creative topology produces twenty genuinely varied finished questions per batch without a per-question Composer call? Compare four isolated five-question strategies against simpler and more expensive alternatives using concrete outputs, prompt isolation, convergence risks, and cost reservations.

## Answer

Use **four isolated Gemini Flash high-thinking calls that each return exactly five finished question texts**. There is no separate concept scout, relation pass, or per-question Composer in Bootstrap Enrichment.

Each call receives only the requested Level, the Question Quality Floor, a compact bank-avoidance summary, the five-question output schema, and one distinct strategy mission:

1. **Concrete life moments** — revealing situations rather than abstract self-description.
2. **Relational mirrors** — closeness, repair, misunderstanding, and being seen.
3. **Tensions and tradeoffs** — choices where two legitimate values pull apart.
4. **Inner signals** — subtle internal evidence that other people may not observe.

The calls do not receive a selected Theme, taxonomy completion targets, sibling outputs, or one another's reasoning. They return only question text; Level checking, semantic comparison, Theme membership, and other metadata happen afterward. Each batch prompt requires five answerable questions with different semantic situations, perspectives, answer spaces, and wording shapes, but those claims are not trusted until downstream evaluation.

The throwaway logic prototype is preserved on branch `codex/prototype-lean-creative-batch` at commit `a7fc021`. It contains twenty concrete Deep-question examples, exposes every reservation and state transition, and compares these topologies:

| Topology | Creative attempts | Illustrative worst-case reservation | Convergence/recovery assessment |
|---|---:|---:|---|
| One call returning twenty | 1 | `$0.04785` | Cheapest, but high within-response anchoring and all-or-nothing failure |
| Four isolated calls returning five each | 4 | `$0.09720` | Recommended balance: distinct strategy priors and five-question failure isolation |
| Four scouts + relation pass + twenty Composers | 25 | `$0.40200` | Reject for bootstrap: exceeds the 12-attempt pilot limit before evaluation |

The dollar figures apply the researched list prices to explicit illustrative input and total-generated-token caps. They are not live measurements and become valid Budget Reservations only when the native Gemini adapter can enforce an authoritative total-generated-token bound. The four-call topology leaves `$0.02280` of the pilot's creative envelope after protecting `$0.08` for evaluation; the expensive topology cannot fit.

Each successful response must structurally contain exactly five non-empty, locally unique question strings. A malformed or ambiguous call yields no questions from that batch, retains Unknown Spend where applicable, and is not automatically retried. Other isolated batches may still complete. Deterministic normalization may remove exact duplicates, but no automatic rewrite or Composer repair is allowed.

This prototype establishes the topology, not its empirical acceptance yield. The 20-candidate costed pilot must validate that the four strategies actually satisfy the Question Quality Floor and variety target before production scaling.
