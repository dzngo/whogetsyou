# Question Bank v3 n8n implementation

This directory contains the Git-governed database and workflow sources for the
n8n-native Question Bank described in
[`docs/n8n-question-bank-v3-migration-plan.md`](../../docs/n8n-question-bank-v3-migration-plan.md).

The complete workflow graph exists in the connected n8n instance. The database
contract suite and non-paid pinned path matrix pass. All five required
credentials are created, and all 47 credential-bearing live nodes are bound to
their exact credential IDs. The initial paid qualification failed content
review; two stricter follow-up campaigns now leave 18 manually retained
qualification questions in the authoritative v3 bank. See
[`PAID_QUALIFICATION_REPORT.md`](./PAID_QUALIFICATION_REPORT.md). Run, Control,
and Export are published after the final validation/readback audit passed. The
real structured-output repair qualification passed on execution `2834`. n8n is
now the sole production owner for new Question Bank campaigns.

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
          -> Semantic Judge one candidate at a time with a fresh top 10
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

The first startup applies the numbered SQL migrations in `sql/` and enables pgvector.
`001_question_bank_v3.sql` is the fresh-install snapshot; later numbered files
are the idempotent upgrade path for existing volumes, so evolved function
definitions intentionally appear in both places. Migration `009` blocks
ambiguous provider replay, enforces even mixed targets, persists mission IDs
before Creative calls, and makes grouped metadata application exact and atomic.
PostgreSQL only runs `/docker-entrypoint-initdb.d` for an empty data directory,
so upgrade an existing named volume explicitly:

```bash
./scripts/apply-sql-migrations.sh
```

The runner records successfully applied files in `qb3.schema_migrations` and
does not replay them on later runs. It discovers `POSTGRES_USER` and
`POSTGRES_DB` from the running container; set `QB3_POSTGRES_USER` or
`QB3_POSTGRES_DB` only when intentionally overriding those values.
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
- **Simplified Custom Auth** (`httpTemplatedCustomAuth`; called Templated Custom
  Auth in older documentation) for the OpenAI embeddings HTTP request, containing
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

The current connected instance has all five credentials bound by ID. Credential
IDs are non-secret n8n object references; the checked-in workflow sources record
them so rebuilding this instance cannot silently select a different credential.
Do not publish the launch or control form if those bindings are ever removed.

## Current n8n resources

[`n8n-resources.json`](./n8n-resources.json) records the live Data Table and
workflow IDs created through n8n MCP. All workflows are created in the personal
project and tagged `question-bank-v3`. Internal subworkflows, the shared error
handler, and all three authenticated operator workflows are active.

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

Regenerate the seven standard role wrappers after changing their shared
contract. The Repair router is intentionally maintained separately because it
contains role-schema validation and trace-persistence branches that are not
shared by the ordinary wrappers:

```bash
node scripts/render-role-workflows.mjs
```

CI or local verification can check that the committed wrappers match the
generator without rewriting them:

```bash
node scripts/render-role-workflows.mjs --check
```

Run the database contract suite:

```bash
./test-sql.sh
```

No paid model test may be run without explicit authorization. Before any
workflow is published, validate it, read it back from n8n, inspect its saved
connections and credential IDs, and attach the published shared error handler.

The implementation has completed validation and readback for all 38 active
workflows (247 nodes), credential binding, and the non-paid pinned
path matrix documented in
[`PINNED_TEST_REPORT.md`](./PINNED_TEST_REPORT.md). A full live audit checked
41 Postgres nodes, three Basic Auth form triggers, one Simplified Custom Auth
embedding request, one Gemini node, and one native OpenAI node with zero binding
mismatches. The shared error recorder is published and attached to all 37
other live Question Bank v3 workflows. Semantic admission now refreshes
neighbours before every candidate, database admission enforces terminal state
and per-level quotas, and batch completion terminalizes unused candidates. The
provider-attempt workflows contain guarded same-provider repair calls. They
validate, their saved connections were read back, their active versions match
the drafts, and their paid repair-path qualification passed.

Completed provider attempts are resume-safe: the budget reservation contract
returns the persisted `agent_runs` result instead of calling the provider again.
If a worker encounters a still-reserved attempt with no durable result during
its 30-minute lease, it returns `in_flight` without replaying or abandoning the
call. The provider-attempt boundary then drops that item, so a duplicate worker
cannot advance or mutate its batch while the original lease holder is still
running. After that lease expires, the reservation is treated conservatively as
`unknown_spend` and is never purchased again automatically.
If the base result was schema-failed but a linked repair child succeeded, resume
returns the repaired original-role payload and makes no second repair call.
Completed embedding attempts similarly return the stored candidate vector's
current top-ten neighbours without purchasing a second embedding. New embedding
successes and provider failures persist a compact `agent_runs` trace containing
the input text, model, usage, transport outcome, and returned neighbour evidence;
the full 1536-number vector remains only in the candidate row.
Released and unknown provider outcomes also persist an `agent_runs` trace with
the rendered prompt, raw failure, and retry classification, so resume never
silently repeats the same attempt. The generative Gemini roles reserve `$0.028`
per attempt, above the declared `$0.02736` worst case of their waterfall.
Malformed JSON or schema-mismatched output is persisted as `schema_failed`, then
sent to the same-provider Repair Agent under a separate reservation and linked
trace. A malformed Repair Agent response terminates as operationally unresolved
instead of recursing.

Mission Writer output is accepted only when slots 1–4 are unique and exactly
match the batch's requested level mix. Quality and escalation output must cover
each candidate ID in the current group exactly once; otherwise the whole group
is isolated as operationally unresolved. The asynchronous campaign worker
registers its execution ID, allowing the shared error handler to persist the
campaign ID and transition an escaped failure to `database_error`.
