# Research Provider Cost Accounting Signals

Type: research
Label: wayfinder:research
Status: resolved
Assignee: provider_cost_research
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)

## Question

Which request, response, usage, cached-token, reasoning-token, retry, pricing, and model-identity facts do the configured OpenAI and Gemini APIs expose through their official SDKs, and which of those facts can support pre-call reservation, post-call reconciliation, and a hard cross-provider Enrichment Budget without silently exceeding it?

## Answer

The primary-source findings are recorded in [`Provider Cost-Accounting Signals for Question-Bank Enrichment`](../../../docs/research/provider-cost-accounting-signals.md).

A hard cross-provider Enrichment Budget requires one application-owned atomic reservation ledger shared by every worker. Each provider attempt reserves its worst-case list-price cost before sending, reconciles successful native usage afterward, and retains its full reservation as unknown spend after a timeout or transport-ambiguous failure. An ambiguous failure is not retried by default because the provider may already have generated and billed the response.

OpenAI Responses supports budget-grade reservation when input is counted or conservatively bounded and every request sets a reasoning-inclusive `max_output_tokens`. Native Gemini responses expose input, cached, visible-output, and thought usage for reconciliation, but the current beta OpenAI-compatibility route does not document a sufficiently complete thought/cache mapping or a tight total-generated-token ceiling. The redesigned system therefore needs a native Gemini usage adapter before it can claim a hard `$2` budget; otherwise the Gemini portion is only a guarded estimate.

Provider project spend caps remain secondary protection because both providers document enforcement delay or possible overrun. The current audit record is insufficient because it does not retain token usage, price-catalog identity, reservations, actual cost, or unknown spend.
