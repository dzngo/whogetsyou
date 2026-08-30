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

The `question_bank` package builds the future Question Bank offline. It does not alter live gameplay question generation or sampling.

The role routing is intentionally mixed-model:

- Creative scouts, composers, and the taxonomy candidate author use `gemini-3.5-flash-high`, which resolves to Gemini 3.5 Flash with high thinking.
- Evaluation, relation, challenge, theme-classification, and taxonomy-judging roles use `gpt-5.4-mini-high`.

Both providers use structured outputs. Each isolated invocation records its provider model, reasoning setting, prompt/schema/context versions, hashes, status, and concise reason codes. Private chain-of-thought is neither requested nor stored.

Credentials are loaded from the existing `.env` file as `GOOGLE_API_KEY` and `OPENAI_API_KEY`.

Initialize local relational stores:

```bash
python -m question_bank --data-dir storage/question_bank init
```

Install the human-confirmed initial Aspect/Perspective taxonomy and a JSON Coverage Plan before autonomous operation:

```bash
python -m question_bank --data-dir storage/question_bank taxonomy-install \
  --aspect self_understanding \
  --perspective restoration

python -m question_bank --data-dir storage/question_bank coverage-plan-install \
  --taxonomy-version <taxonomy-version-from-the-previous-command> \
  --regions-file coverage-regions.json
```

Run one bounded enrichment brief against a fixed snapshot:

```bash
python -m question_bank --data-dir storage/question_bank enrich \
  --level deep \
  --gap-json '{"region_id":"identity-deep-restoration","aspect_id":"self_understanding","perspective_id":"restoration"}' \
  --taxonomy-version taxonomy-v1 \
  --concepts-per-scout 5
```

`autonomous` reads the current released taxonomy and Coverage Plan, selects the next gap itself, and stops at explicit iteration, proposal, or review-queue budgets. `--run-completion-challenge` enables the three-round/two-strategy saturation test when coverage is healthy. `--auto-publish` still fails closed unless the candidate passes taxonomy, coverage, distinctness, index-rebuild, policy-revalidation, Reference Example, and spot-check gates.

Reference Examples are imported separately—never from the existing eval corpus—then human-confirmed once and regression-tested under the exact release policy versions. `reference-import`, `reference-confirm`, and `reference-regression-record` manage those records.

`review-list`, `review-resolve`, `release-build`, `release-verify`, `release-publish`, `release-rollback`, and `status` expose the remaining operator workflows. Human Accept resumes Theme classification and admission; a human edit creates a new proposal version and re-enters full evaluation. Run `python -m question_bank --help` for all arguments.
