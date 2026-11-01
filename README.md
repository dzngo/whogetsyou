# Who Gets You?

## 1. Core Game Rules

### 1.1 Objective
Celebrate how well friends “get” one another.

### 1.2 Setup
1. Each person enters a display name.
2. One player becomes the Host, creates/reuses a room, and sets:
   - **Language**
   - **LLM provider/model**
   - **Target score** (default 10 for two players and 100 for standard mode, editable in lobby)
3. Host shares room code; others join.
4. Minimum players to start: **2**. Exactly two players use two-player mode; three or more use standard mode.
5. Storyteller order is randomized once at game start, then rotates every round.

### 1.3 Turn Structure
In standard mode, each round follows this flow:
1. **Theme selection** — Storyteller picks a theme (always dynamic).
2. **Level selection** — Storyteller picks depth: **Shallow** or **Deep**.
3. **Question proposal** — A curated question is sampled; the Storyteller can edit, change, then confirm. Listeners can save questions for later turns.
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

In two-player mode, both players submit answers privately. The Storyteller judges the Listener's answer; a correct Shallow answer earns the Listener 1 point and a correct Deep answer earns 3. Matching answers are allowed. The target is checked after both players have had an equal number of Listener turns. The highest score wins, or equal scores tie. Incomplete rounds award no points.

Standard mode depth multiplier:
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
- Standard mode: any player reaches/exceeds the target score. Two-player mode: the target is reached and both players have had equal Listener turns.
- Host clicks **End game** (current top score wins).

---

## 2. Streamlit Flow Overview

### 2.1 Entry Screen
Landing screen with two actions:
- **Create room**
- **Join room**

### 2.2 Host Flow
1. **Host name and room name**
   - If room exists: host can **Reuse room** or **Change settings**
2. **Language + LLM selection**
3. **Lobby**
   - Shows room summary and connected players
   - Allows max-score update and player removal
   - Start button enabled when at least 2 players are connected

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

Standard mode phases:
1. **Theme Selection** — Storyteller only
2. **Level Selection** — Storyteller only (Shallow/Deep)
3. **Question Proposal** — Storyteller can edit/change/confirm
4. **Answer Entry** — Every player submits one answer; no author names shown here
5. **Guessing** — Listeners guess the Storyteller answer from all submitted answers
6. **Reveal & Scoring** — Show Storyteller answer, listener guesses, and per-round point deltas
7. **Results** — Final scoreboard and winners

In two-player mode, both players submit answers, then the Storyteller judges the Listener's answer before reveal. The final results show each player's Listener accuracy and correct answers by level.


## Question bank and statistics

In development, gameplay reads `storage/curated_question_bank/questions.json`; in production (`WGY_ENV=production`), it reads the `question_bank` table from Neon. Selection starts uniformly among eligible questions. After five consecutive skips in a turn, Gemini proposes an internal search question and OpenAI embeddings rank eligible bank questions; the five closest are shown one at a time. Failures fall back to random sampling. Aggregate statistics do not yet affect sampling. Each game keeps per-player seen and saved questions and a game-wide list of confirmed questions. Saved questions retain the displayed text and can be played again.

Question events persist separately from room state. Development (the default `WGY_ENV=development`) writes to `storage/question_events_dev.sqlite3`. For production, set `WGY_ENV=production` and `QUESTION_DB_NEO_URL` to a Neon PostgreSQL connection string with permission to create and insert into `question_events`; install the dependencies in `requirements.txt`. Never use the production URL for development. The `question_events` table stores anonymous action events, question IDs, timestamps, and unique event IDs, not names, answers, or edited text. The `question_counters` database view provides per-question counts, including zero-count entries for the current bank, and `question_text` contains the original bank `text`, not `display_template`, translated text, or a player-edited version. It is calculated from the events, so existing events are included and retries cannot inflate counts. The catalog is synchronized at app startup and when bank IDs or original question texts change. Assisted sampling requires GOOGLE_API_KEY and OPENAI_API_KEY. Development reads the local `storage/curated_question_bank/embeddings.sqlite3` cache; production reads the `question_embeddings` table in Neon using pgvector. After changing original question texts or adding questions, rebuild the local vectors with `.venv/bin/python skills/curate-game-questions/scripts/neighbours.py --sync`, upload the updated bank using the command below, and then run `.venv/bin/python -m scripts.sync_question_embeddings_neon`. The embedding sync verifies the bank and existing vectors and does not regenerate embeddings. If assisted selection fails, the app uses random sampling and retries after five more skips; server logs record the error type without question text or credentials. Pending events are written in one transaction per batch; events awaiting a temporary database recovery are retained in the room state and retried. The room JSON file itself must also be placed on persistent storage; it is not a multi-instance database.


To upload or update the curated bank in Neon, set `QUESTION_DB_NEO_URL` and run `.venv/bin/python -m scripts.sync_question_bank_neon`. The command upserts the full bank and verifies it in one transaction, and also initializes counter records using each question's original `text`. It does not delete questions already in Neon that are absent from the local bank. The upload always reads the local JSON file, including when `WGY_ENV=production`.
