# Question Bank v3 n8n implementation

This directory contains the Git-governed database and workflow sources for the
n8n-native Question Bank described in
[`docs/n8n-question-bank-v3-migration-plan.md`](../../docs/n8n-question-bank-v3-migration-plan.md).

The complete draft workflow graph now exists in the connected n8n instance and
all 38 checked-in workflow definitions pass the n8n SDK validator. The database
contract suite passes in disposable PostgreSQL. The drafts intentionally remain
inactive: credentials must be created and bound, deterministic n8n executions
must be tested, and a paid 20-accepted-question qualification campaign requires
separate explicit authorization.

## Visible production flow

```text
Run Question Bank campaign (authenticated form)
  -> Initialize campaign + freeze prompt/runtime registry
  -> Continue campaign (bounded internal batch loop)
      -> Process one batch
          -> Distribution snapshot
          -> Observation Agent
          -> Mission Writer Agent
          -> Creative Agent x4 sequentially (5 questions each)
          -> Quality Judge groups of 10
          -> Quality Escalation for uncertain cases only
          -> Exact normalized duplicate check per candidate
          -> text-embedding-3-small + top-10 pgvector retrieval
          -> Semantic Judge groups of 5
          -> Deterministic admission / rejection / review
          -> Theme and Metadata Agent after admission
          -> Complete batch + refresh global statistics
```

`n8n-resources.json` is the authoritative map from these names to the live n8n
draft IDs. Open **Process one Question Bank batch** for the complete agent and
prompt flow. Open an individual execution, then enter a named Agent subworkflow
to inspect its typed input, fully rendered credential-free prompt, raw provider
response, structured response, model, usage, and reconciled cost.

Git snapshots of the two operator-edited tables live in
`registries/prompt-registry.json` and `registries/runtime-registry.json`. They
exclude n8n-managed row IDs and timestamps and contain no credentials.

## Local PostgreSQL

Copy `.env.example` to `.env`, replace the password, and start the database:

```bash
docker compose up -d
```

The first startup applies `sql/001_question_bank_v3.sql` and enables pgvector.
The default host port is `55432`. In n8n, create a credential of type
**Postgres** pointing to this database from the network where n8n runs. Do not
put the password in a workflow field.

To test the schema in a disposable container:

```bash
./test-sql.sh
```

If n8n itself runs in Docker Desktop, use `host.docker.internal` and port
`55432` in the Postgres credential. `localhost` from inside the n8n container
means the n8n container, not the Mac host.

## n8n credentials required

Create or share these credential types with the n8n project before binding and
testing workflows:

- **Postgres** for the Question Bank v3 database;
- **OpenAI API** for GPT;
- **Google Gemini (PaLM) API** for Gemini Flash Lite roles.
- **Templated Custom Auth** for the OpenAI embeddings HTTP request, containing
  only an `Authorization: Bearer …` header. This preserves the raw embedding
  usage object required for exact budget reconciliation.
- **Basic Auth** for the two operator forms. These forms start paid work or
  change campaign state and must not be exposed anonymously.

The workflow definitions must reference credential IDs. Secrets never belong in
workflow JSON, prompts, execution data, or this repository.

Use these display names so the checked-in workflow sources remain easy to
match with the n8n UI:

- `Question Bank v3 Postgres`
- `Question Bank v3 OpenAI`
- `Question Bank v3 Gemini`
- `Question Bank v3 OpenAI HTTP`
- `Question Bank v3 Operator Basic Auth`

The repository root `.env` is deliberately not read or copied by the
implementation. Enter the existing API keys through n8n's Credentials UI.

After creating the credentials, bind every unresolved credential reference in
the n8n drafts. Do not publish the launch or control form while its Basic Auth
credential is unbound.

## Current n8n resources

[`n8n-resources.json`](./n8n-resources.json) records the live Data Table and
workflow IDs created through n8n MCP. All workflows are created in the personal
project and tagged `question-bank-v3`. They remain inactive until credentials
are bound and the non-paid qualification checks pass.

The role workflows are deliberately thin and visible:

```text
typed role input
  -> load immutable campaign prompt
  -> invoke explicitly budgeted provider attempt
  -> reconcile usage
  -> persist rendered prompt + raw/structured output
```

Runtime settings are operator-visible in the **Question Bank v3 Runtime
Registry** Data Table. A new campaign freezes both registry tables, so later
edits affect only later campaigns. Current defaults are Gemini 3.5 Flash-Lite
with high thinking for Observation, Mission Writer, and Creative; GPT-5.4 mini
for quality, semantic, and metadata roles; and `text-embedding-3-small` at 1536
dimensions for retrieval. Confirmed Gemini `503 UNAVAILABLE` responses follow
the explicit four-attempt waterfall recorded in the migration plan.

The native Gemini AI Agent model connector in n8n 2.38.1 does not expose a
thinking control. The implementation therefore uses the native direct Gemini
node with dynamic thinking (`thinkingBudget = -1`) and groups/names it as the
role agent. This preserves the requested high-thinking behavior, visible raw
response, exact usage accounting, and explicit 503 fallback control. OpenAI
roles similarly use the native Responses node with strict JSON Schema output.

## Development checks

Regenerate the seven standard role wrappers and the repair router after
changing their shared contract:

```bash
node scripts/render-role-workflows.mjs
```

Run the database contract suite:

```bash
./test-sql.sh
```

No paid model test may be run without explicit authorization. Before any
workflow is published, validate it, read it back from n8n, inspect its saved
connections and credential IDs, and attach the published shared error handler.

The current implementation has completed validation and saved-connection
inspection. Credential binding, pinned non-paid execution tests, shared error
handler publication/attachment, and the paid qualification gate remain operator
steps because they depend on secrets or incur provider cost.

Completed provider attempts are resume-safe: the budget reservation contract
returns the persisted `agent_runs` result instead of calling the provider again.
Completed embedding attempts similarly return the stored candidate vector's
current top-ten neighbours without purchasing a second embedding.
Malformed JSON or schema-mismatched output is persisted as `schema_failed`, then
sent to the same-provider Repair Agent under a separate reservation and linked
trace. A malformed Repair Agent response terminates as operationally unresolved
instead of recursing.
