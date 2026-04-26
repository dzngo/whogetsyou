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
   - Storyteller submits the true answer.
   - Each listener submits one plausible answer.
   - Duplicate answers are blocked using exact-match checks.
5. **Guessing** — All listeners see the full answer list and guess which one is the Storyteller’s true answer.
6. **Reveal & scoring** — True answer is revealed, listener guesses are shown, points are applied.
7. **Rotation** — If no winner yet, next Storyteller starts the next round.

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
5. **Guessing** — Listeners guess the true answer from all submitted answers
6. **Reveal & Scoring** — Show true answer, listener guesses, and per-round point deltas
7. **Results** — Final scoreboard and winners
