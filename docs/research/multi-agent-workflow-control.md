# Multi-agent workflow control and visualization

Research date: 2026-09-05. Sources are limited to official documentation and
official repositories.

## Decision

> Superseded on 2026-09-10 by the approved direct ADK cutover in
> `docs/adk-question-bank-migration.md`. The analysis below records the earlier
> decision context and is not current operating guidance.

Do **not** migrate the question-bank pipeline to Google ADK only to obtain a
workflow diagram. Keep `EnrichmentEngine` as the execution authority, keep
Phoenix for per-run prompt/input/output traces, and add a small declarative
workflow description that can render the complete static flow as Mermaid (and
later power a control page).

Google ADK is a credible future orchestration option, especially its new 2.0
graph and dynamic workflows, but it is not currently the best fit for this
system. Its Visual Builder is explicitly experimental, Python-only, edits only
Builder-created agents, generates Agent Config YAML, and does not support some
advanced ADK features. Google also warns that changes made outside the Builder
may be incompatible with it. Those constraints make it a poor representation
of this pipeline's custom budget ledger, provider fallback, semantic batching,
admission rules, and recovery logic. See the official [ADK Visual Builder
documentation](https://adk.dev/visual-builder/).

The desired product is really three related views:

1. **Workflow design:** what can run and which deterministic branches exist.
2. **Run state and controls:** what is running, stopped, staged, rejected, or
   unresolved; start, pause, cancel, and resume; authorized and consumed spend.
3. **Prompt flow:** the exact rendered request and parsed output for every model
   attempt.

No evaluated tool provides all three without adapting the application. Phoenix
already provides the third view well. The current engine and database already
provide the control semantics for the second. A generated graph is the smallest
missing piece.

## Evidence about Google ADK

ADK 2.0 graph workflows provide explicit nodes, edges, branching, state, and
code-only steps. Google positions them as a way to combine deterministic logic
with model reasoning, while dynamic workflows allow normal loops,
conditionals, recursion, parallel work, and automatic node checkpointing. This
is genuinely appropriate orchestration machinery, not merely a chat-agent
wrapper. See [graph-based workflows](https://adk.dev/graphs/) and [dynamic
workflows](https://adk.dev/graphs/dynamic/).

ADK's local web interface includes sessions, state inspection, event history,
an agent structure graph, and the Visual Builder. However, Google says ADK Web
is for development/debugging rather than production. The Builder supports the
common LLM, sequential, parallel, and loop components, but its documented
limitations mean that the picture is not necessarily the complete executable
truth for advanced workflows. See [ADK Web](https://adk.dev/runtime/web-interface/)
and [Visual Builder](https://adk.dev/visual-builder/).

ADK has good trace portability. It emits OpenTelemetry GenAI spans over OTLP,
including agent, workflow, tool, and model-call hierarchy, request parameters,
response details, and token usage. Those spans can be sent to any compatible
backend, so an ADK experiment could continue using Phoenix rather than forcing
a move to Google Cloud Trace. Full message capture is sensitive and separately
configurable. See [ADK activity traces](https://adk.dev/observability/traces/).

Mixed Gemini and OpenAI execution is possible, but the Python path to OpenAI is
through LiteLLM; direct OpenAI Responses support is currently documented for Go
and marked experimental. This inserts another adapter between the current
Python engine and OpenAI, so provider-specific response identity, usage,
reasoning-token accounting, structured-output behavior, and retry semantics
would need to be revalidated. See [OpenAI models for ADK](https://adk.dev/agents/models/openai/)
and [ADK model integrations](https://adk.dev/agents/models/).

ADK supports recovery, but it does not remove the hard distributed-systems
work. Its resume documentation says Custom Agents require explicit resume
support, and its guarantees allow tool re-execution, so side-effecting tools
still need duplicate prevention. No general first-class, cross-provider dollar
budget ledger is documented. The existing engine's reservation/reconciliation,
unknown-spend handling, idempotency keys, and provider-specific fallbacks would
therefore remain custom code. See [resume stopped agents](https://adk.dev/runtime/resume/).

Google Cloud Agent Runtime and Cloud Trace add managed deployment, metrics, and
prompt/response inspection, but they are operating and observability services,
not a visual authoring system for this workflow. Capturing complete prompt and
response bodies also provisions Cloud Storage/logging infrastructure and sends
the data into the user's Google Cloud project. See [Cloud prompt/response
collection](https://docs.cloud.google.com/trace/docs/collect-view-multimodal-prompts-responses)
and [Agent Engine monitoring](https://cloud.google.com/agent-builder/agent-engine/manage/monitoring).

## Comparison

| Option | Static workflow illustration | Runtime control and recovery | Prompt I/O tracing | Gemini + OpenAI | Local operation | Migration cost |
|---|---|---|---|---|---|---|
| Current engine + Phoenix + generated graph | Exact if generated from one declarative definition | Already implements application-specific budgets, idempotency, admission, pause/resume, and recovery | Already implemented in Phoenix | Native provider adapters already verified | Fully local | Low |
| Google ADK 2.0 + Phoenix | Strong graph/dynamic runtime; Visual Builder is experimental and incomplete for advanced features | Checkpoint/resume exists, but budget and idempotent side effects remain application work | Portable OTLP traces; can retain Phoenix | Gemini native; Python OpenAI via LiteLLM | Framework/Web can run locally | High: rewrite orchestration and revalidate accounting/provider behavior |
| LangGraph + LangSmith Studio | Best evaluated interactive graph/debug UI: node paths, intermediate state, breakpoints, time travel, prompt editing | Strong checkpoint persistence and durable execution; explicitly requires idempotent side effects | Detailed prompts, outputs, tools, and metrics | Provider-independent graph; model integrations are selectable | Runtime can be local, but Studio requires a LangSmith account | High: rewrite orchestration and integrate the ledger/store |
| OpenAI Agents SDK | Graphviz shows agents, tools, MCP servers, and handoffs, not arbitrary deterministic application branches | Code orchestration is supported; durable long-running work is delegated to integrations such as Temporal, Dapr, Restate, or DBOS | Strong built-in agent/model/tool traces | Supports mixed providers through adapters, with feature caveats | SDK can run locally; default trace UI is hosted, custom exporters exist | Medium-high, with little gain for this pipeline |
| Google Agent Runtime + Cloud Trace | Trace waterfall, not an editable workflow design | Managed runtime rather than this application's control model | Strong cloud tracing and content analytics | Can host supported frameworks/providers | Cloud service | High plus cloud infrastructure |

Official references for the alternatives:

- LangGraph models workflows as explicit state, nodes, and edges, and can render
  Mermaid/PNG diagrams: [Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api).
- LangSmith Studio visualizes graph architecture, traversed nodes, intermediate
  states, prompts, breakpoints, and time travel: [Studio overview](https://docs.langchain.com/langsmith/studio)
  and [Studio observability](https://docs.langchain.com/langsmith/observability-studio).
- LangGraph persists checkpoints and completed work, while its own guidance
  still requires idempotency for operations that may re-execute:
  [persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
  [Functional API durability](https://docs.langchain.com/oss/python/langgraph/functional-api).
- OpenAI's visualization covers agents, tools, MCP servers, and handoffs:
  [Agents SDK visualization](https://openai.github.io/openai-agents-python/visualization/).
  Its tracing captures LLM calls, tools, handoffs, guardrails, and custom spans,
  while durable workflows use separate runtime integrations: [tracing](https://openai.github.io/openai-agents-python/tracing/)
  and [running agents](https://openai.github.io/openai-agents-python/running_agents/).
- Phoenix is an open-source OpenTelemetry trace, prompt, evaluation, and
  experiment UI that can be self-hosted; it is observability rather than the
  workflow executor: [Phoenix overview](https://arize.com/docs/phoenix/) and
  [self-hosted configuration](https://arize.com/docs/phoenix/self-hosting/configuration).

## Recommended architecture

Introduce a read-only **workflow manifest** owned by the repository. It should
describe each node and edge, including:

- agent or deterministic module;
- provider, model, thinking level, and prompt-template identifier;
- input/output schema identifiers;
- success, rejection, uncertainty, budget-exhaustion, and provider-failure
  routes;
- retry/fallback policy;
- whether a node is advisory or admission-affecting.

The engine should either consume this manifest for the fields it already treats
as configuration, or verify at startup that it matches the executable
configuration. One renderer can then produce Mermaid for documentation and
JSON for a small dashboard. The dashboard can combine:

```text
Workflow graph node
  -> current run status and record counts from the question-bank database
  -> exact invocation spans in Phoenix
  -> prompt template + exact rendered prompt + parsed output
```

This yields an accurate workflow picture without surrendering the mechanisms
that protect cost and data quality. It also creates a clean migration boundary:
individual manifest nodes could later be wrapped in LangGraph or ADK nodes
without rewriting provider adapters, the budget ledger, or admission logic all
at once.

## When to reconsider ADK

Run a small ADK proof of concept only if one of these becomes a real product
need:

- non-engineers must visually author and modify workflows;
- deployment is moving to Google's managed agent runtime;
- ADK Visual Builder gains stable support for ADK 2.0 graph/dynamic workflows;
- the team accepts LiteLLM for OpenAI calls and verifies exact accounting,
  structured output, retries, and model identity against the existing adapters.

For that proof of concept, wrap a single non-mutating advisory path—such as
observed-diversity analysis and next-mission creation—rather than the admission
or budget path. Export ADK OTLP traces to the existing Phoenix instance and
compare the resulting prompt visibility, failure behavior, and cost evidence
before considering a larger migration.
