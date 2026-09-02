# Provider Cost-Accounting Signals for Question-Bank Enrichment

Research date: 2026-09-01. Scope: the question-bank routing currently configured
in this repository: `gemini-3.5-flash-high` resolves to
`gemini-3.5-flash` with high thinking, and `gpt-5.4-mini-high` resolves to
`gpt-5.4-mini` with high reasoning. No paid model calls were made.

## Conclusion

Both providers return enough usage information after a successful native API
response to calculate list-price token cost. That supports accurate per-call
post-call reconciliation.

A genuinely hard `$2` cross-provider run budget is possible only as an
**application-owned reservation ledger**, with these constraints:

1. Every provider attempt must acquire an atomic worst-case reservation before
   it is sent.
2. Every request must have a documented, finite generated-token ceiling.
3. A timeout or connection loss must retain its entire reservation as
   `spend_unknown`; it must not be treated as free and automatically retried.
4. The run must stop when actual cost plus live reservations plus unknown-spend
   reservations reaches the authorized budget.
5. All enrichment workers must share the same ledger. Concurrent calls made
   outside that ledger are outside the guarantee.

OpenAI's Responses API supplies both a complete usage breakdown and a documented
output ceiling that includes reasoning tokens. The current Gemini path uses
Google's beta OpenAI-compatibility endpoint. Google documents that endpoint's
request mapping, but not a budget-grade mapping of all native usage fields.
Google's native APIs explicitly expose thought and cache usage. Therefore the
cost-safe design should use native Gemini usage metadata (preferably the current
Interactions API) rather than depend on the compatibility response shape.

Provider/project spend limits should be a second safety layer, not the run
budget. OpenAI warns that hard-limit enforcement is not instantaneous and may
slightly overrun. Google warns of roughly ten minutes of billing latency and
possible overages. ([OpenAI spend-limit troubleshooting](https://help.openai.com/en/articles/6614457),
[Gemini billing and spend caps](https://ai.google.dev/gemini-api/docs/billing#spend-caps))

## Current Repository Gap

The local wrapper currently keeps only `response_id`, `reported_model`, and
`system_fingerprint` from a completed response. It does not retain the response
usage object. Consequently, the existing invocation audit can count application
attempts but cannot reconstruct provider token cost.

The wrapper disables SDK retries, which is helpful, but `AgentRunner` performs
one outer retry. Each outer retry is a new provider request. A timed-out first
attempt may have reached the provider and consumed tokens even though no usage
object reached the application.

## Signals Available from OpenAI

### Successful Responses

For a Responses API result, `usage` contains:

- `input_tokens`
- `input_tokens_details.cached_tokens`
- `input_tokens_details.cache_write_tokens` when applicable
- `output_tokens`
- `output_tokens_details.reasoning_tokens`
- `total_tokens`

The response also carries `id`, `model`, status, timestamps, and other request
configuration. `reasoning_tokens` are a subset of `output_tokens`, not an
additional quantity to add again. OpenAI states that internal reasoning tokens
count toward output usage and are billed as output tokens.
([Responses API response/usage schema](https://developers.openai.com/api/reference/resources/responses/methods/retrieve),
[OpenAI token accounting](https://help.openai.com/en/articles/4936856))

The official Python SDK exposes the same fields in `ResponseUsage`. Its Chat
Completions `CompletionUsage` equivalent contains `prompt_tokens`,
`prompt_tokens_details.cached_tokens`, `completion_tokens`, and
`completion_tokens_details.reasoning_tokens`.
([Responses usage type](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_usage.py),
[Chat Completions usage type](https://github.com/openai/openai-python/blob/main/src/openai/types/completion_usage.py))

### Pricing for the Configured Judge

As of the research date, standard `gpt-5.4-mini` text pricing per one million
tokens is:

| Category | USD / 1M tokens |
|---|---:|
| Uncached input | $0.75 |
| Cached input | $0.075 |
| Output, including reasoning | $4.50 |

Regional-processing endpoints add a 10% uplift. The model accepts `none`, `low`,
`medium`, `high`, and `xhigh` reasoning effort. The alias has a listed snapshot,
`gpt-5.4-mini-2026-03-17`; retaining both the requested alias and returned model
identity is important for reproducibility.
([GPT-5.4 Mini model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini))

For one standard call, list-price reconciliation is:

```text
uncached_input = input_tokens - cached_tokens

cost_usd =
  uncached_input * 0.75 / 1_000_000
  + cached_tokens * 0.075 / 1_000_000
  + output_tokens * 4.50 / 1_000_000
```

Do not add `reasoning_tokens` again; they are already included in
`output_tokens`.

### Pre-call Reservation

OpenAI provides a Responses input-token counting endpoint for the complete
request shape. More importantly, `max_output_tokens` is documented as an upper
bound that includes both visible response tokens and reasoning tokens.
([Responses input-token counting](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens),
[Responses `max_output_tokens`](https://developers.openai.com/api/reference/resources/responses/methods/create))

For the enrichment workload, which does not use paid tools, a conservative
reservation can therefore assume no cache hit:

```text
openai_reservation =
  counted_or_upper_bound_input * uncached_input_rate
  + configured_max_output_tokens * output_rate
  + any applicable regional uplift
```

The request must explicitly set `max_output_tokens`; leaving it unset defeats a
small hard budget because `gpt-5.4-mini` supports up to 128,000 output tokens.

### Later Aggregate Reconciliation

OpenAI's organization Usage API can report completion input, cached input,
output, model-request counts, project, API key, model, batch state, and service
tier in time buckets. Its Costs API reports aggregate monetary cost. These are
useful for detecting ledger drift, but they are aggregated rather than a
per-response billing receipt, and require administrative access.
([Organization completion usage](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions),
[Organization usage and costs](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage))

## Signals Available from Gemini

### Successful Native Responses

Gemini's current Interactions API reports:

- `total_input_tokens`
- `total_cached_tokens`
- `total_output_tokens`
- `total_thought_tokens`
- `total_tool_use_tokens`
- `total_tokens`
- per-modality breakdowns

It also returns an interaction `id`, `model`, status, and timestamps. Google
explicitly says thinking cost is the sum of visible output tokens and full
thought tokens, even though full thoughts are not returned.
([Interactions API usage schema](https://ai.google.dev/api/interactions-api-v1),
[Gemini thinking and pricing](https://ai.google.dev/gemini-api/docs/thought-signatures#pricing))

The older `generateContent` response provides the corresponding
`promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`,
`thoughtsTokenCount`, `toolUsePromptTokenCount`, `totalTokenCount`, and
`modelVersion` fields.
([GenerateContent response and UsageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata))

### Pricing for the Configured Creative Model

As of the research date, standard paid-tier `gemini-3.5-flash` text pricing per
one million tokens is:

| Category | USD / 1M tokens |
|---|---:|
| Uncached input | $1.50 |
| Output, including thinking | $9.00 |
| Cached input | $0.15 |
| Explicit cache storage | $1.00 per 1M token-hours |

Batch pricing is $0.75 input, $4.50 output including thinking, and $0.075 cached
input, but it is asynchronous and is not the repository's current call path.
([Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash))

For one standard, tool-free native call, list-price reconciliation is:

```text
uncached_input = total_input_tokens - total_cached_tokens
generated = total_output_tokens + total_thought_tokens

cost_usd =
  uncached_input * 1.50 / 1_000_000
  + total_cached_tokens * 0.15 / 1_000_000
  + generated * 9.00 / 1_000_000
  + explicit_cache_storage_cost_if_any
```

`total_output_tokens` and `total_thought_tokens` are distinct in Gemini's native
schema, so both are charged. This differs from OpenAI's schema, where reasoning
tokens are already inside `output_tokens`.

### Thinking and Pre-call Reservation

Google maps OpenAI-compatible `reasoning_effort="high"` to Gemini high thinking.
Gemini 3.5 Flash high thinking is dynamic: the setting encourages more thought
but does not promise a fixed thought-token quantity. Google recommends medium
for most work and says high allows extended thinking with higher cost.
([Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai#thinking),
[Gemini 3.5 Flash thinking levels](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5#new-default-effort-level))

Google's `countTokens` endpoint can count the input before generation, and its
native response provides actual output/thought usage afterward. However,
`countTokens` only predicts input. The documented model-generation
`max_output_tokens` limits response tokens, while thought tokens are reported
separately. The documentation does not state that this value is a cap on the
sum of response plus thought tokens.
([Gemini token counting](https://ai.google.dev/gemini-api/docs/tokens#count-tokens),
[Interactions generation configuration](https://ai.google.dev/api/interactions-api-v1))

Therefore a low hard-dollar reservation cannot safely treat
`max_output_tokens` as the complete high-thinking cost ceiling without an
additional documented or validated total-generated-token bound. A conservative
implementation must either:

- reserve against an authoritative total-token ceiling for the selected native
  endpoint/model;
- reserve against the model's full possible generated usage, which may be too
  pessimistic for a `$2` run; or
- treat the run budget as a guarded estimate rather than call it a hard budget.

### Compatibility-layer Limitation

The repository currently calls Gemini through Google's
`/v1beta/openai/chat/completions` endpoint and the OpenAI Python SDK. Google says
OpenAI-library support remains beta and recommends its native API when OpenAI
compatibility is not required. Its compatibility documentation does not define
a complete normative mapping from native thought/cache usage into OpenAI
`CompletionUsage` fields.
([Gemini OpenAI compatibility and limitations](https://ai.google.dev/gemini-api/docs/openai#current-limitations))

For a budget ledger, preserve the compatibility route only if tests demonstrate
all required fields for the exact deployed model and SDK. The safer design is a
native Gemini adapter that normalizes native usage metadata into the shared
ledger schema.

### Provider-level Billing Controls

Google supports prepay/postpay plans and experimental project spend caps, but
warns of about ten minutes of billing latency and possible overages. A depleted
prepay balance stops service, but can also overrun during that latency. Google
states that requests returning 400 or 500 errors are not charged; this does not
settle a client-side timeout where the application received no provider status.
([Gemini billing](https://ai.google.dev/gemini-api/docs/billing))

## Retry and Timeout Accounting

The official OpenAI Python client retries connection failures, timeouts, 408,
409, 429, and 5xx responses by default; `max_retries=0` disables those SDK
retries. Its implementation reuses one generated idempotency key across the
internal attempts of a single SDK request.
([OpenAI Python retry documentation](https://github.com/openai/openai-python#retries),
[OpenAI Python retry implementation](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py))

That does not make arbitrary application-level retries free or idempotent. In
the current repository, the outer retry starts another SDK request and does not
persist or reuse a provider idempotency key.

Use these accounting rules:

| Attempt outcome | Ledger action |
|---|---|
| Successful response with usage | Replace reservation with calculated actual cost. |
| Explicit provider rejection known not to be billed | Release reservation and retain failure audit. |
| Timeout, connection loss, malformed response after send, or unknown provider state | Move the full reservation to `spend_unknown`; do not release it. |
| Retry after an unambiguous non-billed failure | Acquire a fresh reservation first. |
| Retry after an ambiguous failure | Normally do not retry. If policy permits it, budget must cover both the unknown first attempt and the new attempt. |

The same policy prevents a response that was generated and billed after a local
60-second timeout from silently exceeding the run budget.

## Required Normalized Ledger Record

Each provider attempt should record at least:

```text
run_id, logical_invocation_id, provider_attempt_id
provider, endpoint, requested_preset, requested_model, reported_model
reasoning_or_thinking_level, service_tier, regional_processing
price_catalog_version, currency
input_tokens, cached_input_tokens
visible_output_tokens, reasoning_or_thought_tokens, total_tokens
reserved_usd, actual_usd, accounting_state
provider_response_id, request_started_at, response_completed_at
retry_of_attempt_id, error_class
```

Provider-specific usage must be normalized carefully:

- OpenAI `output_tokens` already includes `reasoning_tokens`.
- Gemini `total_output_tokens` excludes `total_thought_tokens`; add them for
  generated-token cost.
- Cached tokens are part of total input on both providers; subtract them before
  applying the uncached-input rate.
- `gpt-5.4-mini` has no separately published cache-write charge; keep any
  reported cache-write count for forward-compatible auditing rather than adding
  it to the GPT-5.4 Mini formula.
- Keep requested and reported model identities separately. A price must be
  selected from the reported billable identity and service tier where possible.

The ledger transition and reservation check must occur in one database
transaction:

```text
actual_usd + active_reserved_usd + unknown_reserved_usd
  <= authorized_run_budget_usd
```

If the next attempt cannot satisfy that invariant using its worst-case
reservation, it must not be sent.

## Limits of the Guarantee

An application ledger can guarantee that this enrichment run does not
**authorize** provider attempts beyond its budget. It cannot promise that the
provider invoice will equal the estimate exactly when any of these apply:

- a transport failure prevents receipt of usage;
- pricing or model aliases change without updating the versioned price catalog;
- another process uses the same API project/key outside the ledger;
- the provider applies account-specific credits, free-tier pricing, negotiated
  rates, taxes, regional uplift, or delayed adjustments;
- provider-level spend-cap enforcement is delayed;
- a compatibility layer omits or remaps native usage fields.

For the strongest practical guarantee, use dedicated provider projects or keys
for enrichment, a versioned list-price catalog, native usage responses, no
automatic retry after ambiguous failures, explicit per-request token ceilings,
and provider hard limits set slightly above the application's lower run budget.

## Decision-ready Findings

1. **Post-call accounting:** feasible and exact at published list prices from
   successful native responses for both providers.
2. **OpenAI pre-call reservation:** feasible for this tool-free workload when
   full input is counted/upper-bounded and `max_output_tokens` is mandatory.
3. **Gemini pre-call reservation:** input is countable, but the current
   high-thinking compatibility route does not document a tight cap covering
   billed thought plus visible output. Do not claim a hard dollar cap until
   that gap is closed.
4. **Retries:** timeout/transport errors are financially ambiguous. Preserve
   their full reservation and do not retry by default.
5. **Provider spend controls:** useful defense in depth, not exact run-level
   enforcement because both providers acknowledge delayed enforcement or small
   overages.
6. **Required architectural seam:** a provider-native usage adapter feeding one
   atomic cross-provider budget ledger; model calls must not bypass it.
