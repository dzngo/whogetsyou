# Who Gets You?

## 1. Core Game Rules

### 1.1 Objective
Celebrate how well friends “get” one another.

### 1.2 Setup
1. Each person enters a display name.
2. One player becomes the Host, creates/reuses a room, and sets:
   - **Language**
   - **LLM provider/model**
   - **Target score** (default 100, editable in lobby)
3. Host shares room code; others join.
4. Minimum players to start: **3**.
5. Storyteller order is randomized once at game start, then rotates every round.

### 1.3 Turn Structure
Each round follows this flow:
1. **Theme selection** — Storyteller picks a theme (always dynamic).
2. **Level selection** — Storyteller picks depth: **Shallow** or **Deep**.
3. **Question proposal** — AI suggests a question; Storyteller can edit, regenerate, rephrase, then confirm.
4. **Answer entry** —
   - Storyteller submits the Storyteller answer.
   - Each listener submits one plausible answer.
   - Duplicate answers are blocked using exact-match checks.
5. **Guessing** — All listeners see the full answer list and guess which one is the Storyteller answer.
6. **Reveal & scoring** — Storyteller answer is revealed, listener guesses are shown, points are applied.
7. **Rotation** — If no winner yet, next Storyteller starts the next round.

Question styles:
- **Shallow**: lightweight, realistic, low-pressure prompts about an everyday preference, habit, routine, simple choice, or plausible situation. A generic poll is allowed and humor is optional.
- **Deep**: reflective, emotionally safe prompts that invite a personally true answer.
- **Random 🎲**: wildcard theme for surprising questions.

### 1.4 Scoring Details
Depth multiplier:
- **Shallow = x1**
- **Deep = x2**

Base scoring by listener correctness:
1. **Exactly one listener correct**:
   - Correct listener: `+3 × Mult`
   - Storyteller: `+3 × Mult`
2. **Some (not all) listeners correct**:
   - Each correct listener: `+1 × Mult`
   - Storyteller: `+1 × Mult`
3. **Everyone correct OR nobody correct**:
   - Every listener: `+2 × Mult`
   - Storyteller: `0`

Decoy bonus (stacks with base scoring):
- If a listener’s submitted answer is selected by `N` other listeners, that listener gets:
  - `+N × Mult`

### 1.5 End Conditions
- Any player reaches/exceeds target score.
- Host clicks **End game** (current top score wins).

---

## 2. Streamlit Flow Overview

### 2.1 Entry Screen
Landing screen with two actions:
- **Create room**
- **Join room**

### 2.2 Host Flow
1. **Host name**
2. **Room name**
   - If room exists: host can **Reuse room** or **Change settings**
3. **Language + LLM selection**
4. **Lobby**
   - Shows room summary and connected players
   - Allows max-score update and player removal
   - Start button enabled when at least 3 players are connected

### 2.3 Join Flow
1. **Room code**
2. If room not started: **Player name** -> join lobby
3. If room already started: **Resume player** (select an existing player in room)
4. **Lobby** (pre-game) or direct game resume (in-game)

### 2.4 In-Game Flow
Persistent board elements:
- Room summary
- Scoreboard
- Current Storyteller marker
- Current round/theme/level
- “You are playing as …” identity cue

Phases:
1. **Theme Selection** — Storyteller only
2. **Level Selection** — Storyteller only (Shallow/Deep)
3. **Question Proposal** — Storyteller can edit/regenerate/rephrase/confirm
4. **Answer Entry** — Every player submits one answer; no author names shown here
5. **Guessing** — Listeners guess the Storyteller answer from all submitted answers
6. **Reveal & Scoring** — Show Storyteller answer, listener guesses, and per-round point deltas
7. **Results** — Final scoreboard and winners

---

## 3. Offline Question Bank Enrichment

> **Question Bank v3 runs in n8n.** The implementation starts with an
> empty PostgreSQL/pgvector bank and uses n8n as both the visible orchestrator
> and day-to-day prompt/input/output inspector. See the
> [approved v3 migration plan](docs/n8n-question-bank-v3-migration-plan.md) and
> [local implementation guide](n8n/question-bank-v3/README.md). The ADK,
> Phoenix, SQLite, and v2/v2.1 instructions below describe the legacy system and
> remain available only for explicit historical recovery; they are not a
> production path for new campaigns.

The legacy `question_bank` package remains available for the existing v2/v2.1
banks. It does not alter live gameplay generation or question sampling. n8n is
the sole production owner for new Question Bank campaigns. Google ADK is
disabled by default, and Phoenix remains opt-in historical tooling only.

### 3.1 Legacy v2/v2.1 multi-agent architecture

The architecture deliberately mixes Gemini and GPT while keeping admission authority in deterministic code:

| Stage | Agent or Module | Model and reasoning | Responsibility |
| --- | --- | --- | --- |
| Creative proposal | Four isolated LLM Agents | Gemini 3.5 Flash Lite, high thinking | Each creative strategy returns five finished question texts. Agents do not assign Themes or see sibling output. |
| Quality evaluation | Routine quality LLM Agent | GPT-5.4-mini, medium reasoning | Evaluates clarity, answerability, emotional safety, Level fit, and Deep revelation in two batches. |
| Quality escalation | Uncertainty-only LLM Agent | GPT-5.4-mini, high reasoning | Re-evaluates only genuinely uncertain quality records, including a Deep evaluator abstention. |
| Semantic routing | Local deterministic Module | Pinned FastEmbed model plus lexical metrics | Rejects exact/near copies and authoritatively passes clearly different pairs. |
| Semantic relation | Ambiguity-only LLM Agent | GPT-5.4-mini, high reasoning | Reviews only pairs not safely resolved by the local Module. |
| Metadata | Classification LLM Agent | GPT-5.4-mini, medium reasoning | Assigns zero-to-many Themes plus Aspect and Perspective after question admission, constrained to the configured vocabulary. Tentative values marked uncertain are stored as pending rather than trusted. |
| Observed diversity + next missions | Advisory LLM Agent over local counts | Gemini 3.5 Flash Lite, high thinking | Interprets observed patterns and writes four new missions for the next batch. Cannot set quotas or change admission. |
| Orchestration | Google ADK 2 graph + deterministic Modules | No LLM | Exposes and controls every production stage while existing Python modules retain budgets, evidence, admission, review, and export authority. |

The graph displays campaign initialization, mission planning, four concurrent creative Agents, creative join/proposal persistence, duplicate preflight, routine and uncertainty quality review, local and LLM semantic review, admission, Observation, metadata, final diversity evidence, atomic export, and the batch loop. Only the four creative Agents run concurrently; batches and every downstream stage run sequentially. Candidate text, costs, decisions, and human-review cases stay in the Question Bank SQLite database. ADK stores lightweight local session/event history in SQLite under `.adk/`.

For explicit historical recovery only, enable and run the legacy ADK surface:

```bash
export QUESTION_BANK_ROOT=storage/question_bank_v2.1
export QUESTION_BANK_EMBEDDING_CHECKSUM=<verified-checksum>
export QUESTION_BANK_ENABLE_LEGACY_ADK=1
.venv/bin/adk web --session_service_uri=sqlite:///storage/question_bank_v2.1/.adk/web-sessions.sqlite3 question_bank
```

Select `adk_app` in ADK Web and submit one exact command:

```text
generate campaign=<id> proposal_target=<multiple-of-20> level=<mixed|shallow|deep> bank=v2.1 budget_usd=<positive>
status campaign=<id>
cancel campaign=<id>
resume campaign=<id> budget_usd=<positive>
```

`proposal_target` counts generated proposals processed, not Staged or unique questions. Generate and resume are spending authorizations; the CLI additionally requires `--confirm-paid`. Cancellation is cooperative: an active provider attempt is accounted for, then no new paid attempt starts. Resume adds a fresh authorization and reuses durable progress. It is guarded by a renewable execution lease, preserves Unknown Spend, checks the pinned configuration atomically, and never reprocesses open human-review cases. Status reports reconciled, active, unknown, and remaining USD. In ADK Web, Generate and Resume run in a server-owned session, so closing the browser does not cancel the campaign while the server stays up.

The four creative call slots remain isolated and each generates five finished questions, individually evaluated afterward. Gemini's existing diversity call now also writes the next four missions: two Shallow and two Deep. Each agent receives only its assigned mission, not sibling missions or outputs. Stable role names identify call slots; dynamic missions replace their original fixed strategies. The mission writer sees local distributions (including themes), a bounded question sample, and recent missions. It considers Aspect, Scenario, Perspective, Answer Space, and optional Contrast (alternatives/trade-offs). All dimension hints may be omitted with `null`; theme hints may be empty and never assign membership. Themes are still classified after admission, with multiple memberships allowed and no theme quotas.

For the first batch, or when the latest mission report is unavailable/invalid, Shallow slots rotate ten bootstrap directions: tastes, routines, entertainment, belongings/style, places/travel, shopping/spending, skills/curiosity, social habits, small reactions/quirks, and simple choices. Deep slots fall back to tensions/trade-offs and inner signals. Shared Level guidance always overrides mission suggestions: Shallow accepts simple favorites and habits without stories, self-analysis, relationship repair, or unnecessary exact-event recall. New missions seek different subjects and answers, not increasing complexity.

Mission structure is validated locally: exactly four unique slots with matching Levels, distinct bounded briefs, and optional bounded dimension hints. No mission-review LLM or human approval step is added. `gemini_diversity_advice` evidence saves the report and `next_missions`; `creative_mission` evidence records each assignment, its source, role, mission ID, and report hash. Failed reports cause bootstrap fallback rather than silent reuse of stale missions. Question-quality and repetition gates remain independent. The report uses the existing Gemini call with a 4,000-token estimated generated-token allowance; there is no extra mission-writing call.

Dynamic missions have a new configuration/execution version. Existing bank data is unchanged; do not resume an old configuration's campaign with the new defaults. Start a new campaign ID for the updated contract. A new campaign in an existing root freezes the existing Staged candidate IDs as a comparison baseline for repetition checks and diversity feedback, without merging configurations or budget ledgers.

For 200 Shallow-only proposals in bank v2.1:

```bash
.venv/bin/python -m question_bank.campaign \
  --root storage/question_bank_v2.1 --campaign-id v21-shallow-200 \
  --target 200 --level shallow --authorization-usd 2.60 \
  --checksum-from storage/question_bank_v2.1/question_bank_v2.sqlite3 --confirm-paid
```

`--level` supports `mixed` (default), `shallow`, and `deep`. Single-Level campaigns assign all four creative slots and all four next missions to that Level. `--target` is a multiple of 20; it counts proposals, not guaranteed unique or accepted questions. Exports use campaign-specific filenames and include only new normalized texts. Each question is still evaluated individually. The first run records the fixed comparison IDs and Level selection; continuations must retain both.

The current local semantic policy is `semantic-routing-v5`: local distance requires embedding cosine `< 0.70`, token Jaccard `<= 0.25`, and character cosine `< 0.55`. Exact and lexical near-copy rejection remains unchanged. From the remaining ambiguous comparisons, GPT receives each candidate's strongest neighbour plus additional strong lexical alerts, in calls of at most six pairs. Engine v2.11 removes the former 24-pair batch limit (`pair_overflow`); total work is bounded by the campaign budget and attempt allowance, with a reservation before every call. No selected comparisons are silently dropped to fit a batch limit. The semantic contract defines Scenario, Perspective, and Answer Space explicitly, requires the final verdict to agree with those three labels, limits reason codes to three, and provides 11,000 output tokens for high-reasoning structured output.

If one semantic chunk fails, only candidates whose admission depends on that failed or later chunk become operationally unresolved. Local passes and already resolved candidates continue through staging and metadata. Saved Staged, awaiting-review, operationally unresolved, and `review_budget_exhausted` candidates can be reprocessed under a new configuration without creative calls. Gemini diversity advice may still run after staging.

For a paused shallow campaign, `python -m question_bank.recover_campaign --root storage/question_bank_v2.1 --campaign-id <original-id> --target 800 --cap-usd 6 --confirm-paid --continue-generation` first reprocesses unique saved overflow candidates, then proposes the remaining batches only if recovery finishes without operational failures. The cap must match the original authorization. A frozen recovery plan deducts all original reconciled spending and active/unknown reservations, and chains recovery and further generation under the remainder. Do not resume the original process alongside recovery. Original records remain unchanged; the campaign CSV overlays recovery outcomes without duplicating questions. Omit `--continue-generation` to perform recovery only. The target counts saved proposals, not guaranteed unique or staged questions.

Every provider call uses structured input and output. GPT batch schemas enumerate the exact requested candidate or pair IDs and require the exact record count. GPT calls use low output verbosity and reserve enough output tokens for both reasoning and the complete JSON record set. The system records the provider/model identity, reasoning setting, prompt and schema hashes, native usage, cost evidence, and concise reason codes. It neither requests nor stores private chain-of-thought. LLM Agents cannot mutate trusted bank state or authorize their own spending.

### 3.2 Legacy Phoenix input/output dashboard

Phoenix provides an optional local dashboard for real campaign invocations. The trace hierarchy is Campaign → Batch → workflow stage → Gemini/OpenAI attempt, including model fallback attempts and semantic chunks. Each span shows the exact credential-free logical request passed to the SDK, the parsed structured response, provider, requested and reported model, thinking level, token usage, cost, status, and sanitized error details. Terminal batch and campaign spans are closed immediately. API keys, transport headers, and private chain-of-thought are never captured.

Install and start the local dashboard:

```bash
PHOENIX_WORKING_DIR=storage/question_bank_phoenix \
  PHOENIX_PORT=6006 PHOENIX_GRPC_PORT=4319 \
  uvx --from arize-phoenix==20.8.0 phoenix serve
```

In a second terminal, opt a campaign into tracing and use its normal command:

```bash
export QUESTION_BANK_PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
export QUESTION_BANK_PHOENIX_PROJECT=question-bank-enrichment
# Run the normal question_bank.campaign command (the ADK CLI wrapper).
```

Open `http://127.0.0.1:6006` to inspect Agent inputs and outputs. Tracing is off when `QUESTION_BANK_PHOENIX_ENDPOINT` is unset. Dashboard startup, export, or shutdown failures are logged and never change question admission, budget accounting, or provider retry behavior.

### 3.3 Cost and failure safety

Before network I/O, the deterministic ledger reserves the worst-case list-price exposure. Successful calls reconcile against provider-reported usage. A crash or ambiguous transport result becomes Unknown Spend. The explicit v2.1 exception is a confirmed Gemini 503: try `gemini-3.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.6-flash`, then `gemini-3.5-flash-lite` once more, with 1/2/4-second waits. Each attempt has its model-specific reservation and actual model identity; earlier unknown spend remains charged against the cap. Other errors do not trigger model switching. Gemini SDK automatic retries are disabled so the ledger sees each attempt. Exact application-cache reuse consumes neither a provider attempt nor additional budget.

The production batch normally uses four creative calls, two routine quality calls, optional quality escalation, up to four semantic calls, one advisory diversity call, and one metadata call. Fallbacks consume additional attempts within the explicit campaign limit. Local decisions can remove semantic calls. Diversity advice failures are recorded and do not reverse question admission; local feedback remains available.

Gemini high thinking currently has no documented reasoning-inclusive hard cap. Creative calls use a 3,200-token estimated reasoning-plus-output allowance after live 2,200-token truncation failures. Paid commands therefore require both `--confirm-paid` and the explicit `--allow-estimated-gemini-cap` acknowledgement.

### 3.4 Configuration and operation

Credentials are loaded through `python-dotenv` from the existing `.env` as `GOOGLE_API_KEY` and `OPENAI_API_KEY`; operators and logs must never print them. The pinned FastEmbed artifact checksum is supplied as `QUESTION_BANK_EMBEDDING_CHECKSUM`.

Initialize the v2 store:

```bash
python -m question_bank --root storage/question_bank_v2 init
```

Run a separate v2.1 campaign (five batches, 50 Shallow + 50 Deep proposals; accepted totals may be lower):

```bash
.venv/bin/python -m question_bank.campaign \
  --root storage/question_bank_v2.1 --campaign-id v21-100 \
  --authorization-usd 3.30 \
  --checksum-from storage/question_bank_v2/question_bank_v2.sqlite3 --confirm-paid
```

This creates a separate database and refreshes `generated_100_questions.csv` after every batch. It does not import or mutate the old bank, so deduplication is scoped to this new campaign. The cap is cumulative across its five batches, including fallback attempts. Repeating the same command reuses saved batch reports; it does not silently retry a stopped batch. The final export includes rejected and unresolved proposals with their states, not just Staged Questions. Model pricing is pinned from [Google's pricing documentation](https://ai.google.dev/gemini-api/docs/pricing).

Run one explicitly authorized 20-proposal campaign through the shared ADK graph:

```bash
python -m question_bank --root storage/question_bank_v2.1 campaign-command \
  generate campaign=pilot-001 proposal_target=20 level=mixed bank=v2.1 budget_usd=0.25 \
  --confirm-paid
```

Inspect a durable run without making provider calls:

```bash
python -m question_bank --root storage/question_bank_v2 report <run-id>
```

`resume-pilot` is retired; use `campaign-command resume`. The compatibility `run-pilot` and `run-production-batch` commands create a 20-proposal campaign through the same ADK graph. `reprocess-candidates` remains a provider-backed recovery operation for existing saved candidates, not a new generation campaign. `review-resolve` handles bounded question-specific uncertainty. `snapshot-build`, `release-verify`, `regression-record`, `spot-check-select`, `spot-check-record`, `release-publish`, `release-withdraw`, and `release-rollback` are provider-free release operations. Run `python -m question_bank --help` for the complete command interface.

For a partial campaign CSV while generation is running, use the provider-free exporter:

```bash
python -m question_bank.live_export \
  --database storage/question_bank_v2/question_bank_v2.sqlite3 \
  --output storage/question_bank_v2/generated_800_additional_questions.csv \
  --prefix v5-new-800-batch- \
  --configuration-id config-26b770fcb8557143a1331100
```

Use the intended campaign's idempotency-key prefix and configuration ID. Add `--watch-pid <generator-pid>` to refresh every five seconds until that process exits, including a final refresh. The exporter reads the database without changing it, makes no API calls, and atomically replaces the CSV only when its contents change. It exports up to 400 new unique questions per Level by default (`--per-level` overrides this), excluding normalized texts saved before that campaign. This is a proposal/progress export, not a published bank: rejected, unresolved, and in-progress questions remain visible in `pipeline_state`.

The retired v1 Coverage Plan and Coverage Regions are not generation targets, quality gates, or completion gates. Legacy v1 storage is archive-only and is never imported into trusted v2 state.
