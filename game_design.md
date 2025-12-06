# Who Gets You? 

## 1. Core Game Rules

### 1.1 Objective  
Celebrate how well friends “get” one another. Players earn points for demonstrating empathy, intuition, and clever bluffs. The first player to hit the agreed target score (or the leader when the host ends the session) wins.

### 1.2 Setup  
1. Each person enters a preferred display name.  
2. One player becomes the Host, creates a room, and defines the configuration:  
   - **Gameplay mode** – _Simple_ (only honest answers) or _Bluffing_ (Storyteller must add a decoy).  
   - **Theme mode** – _Static_ (host selects a rotating list that autocycles) or _Dynamic_ (Storyteller picks each turn).  
   - **Level mode** – _Static_ (one depth for the entire session) or _Dynamic_ (Storyteller chooses each round).  
   - **Target score** – default 100, editable.  
3. The Host shares the room code; other players join as Listeners.  
4. When at least two players are connected, the Host starts the game. Storyteller order is randomized once at the beginning and cycles until someone wins.

### 1.3 Turn Structure  
Each round follows the same heartbeat:

1. **Context** – The current Storyteller locks in theme (if dynamic) and depth (if dynamic).  
2. **Prompt** – A single open-ended question is suggested using the AI assistant (Storyteller can edit or regenerate).  
3. **Answers** –  
   - Simple mode: one sincere answer.  
   - Bluffing mode: one sincere answer _and_ one believable trap answer. Optional “Suggest answer/trap” buttons help craft responses.  
4. **Options** – The system turns the answers into multiple-choice options plus carefully balanced distractors. The Storyteller can regenerate if the set feels off, then confirms when satisfied.  
5. **Guesses** – All Listeners pick one option. In Bluffing mode, choosing the trap boosts the Storyteller, so listeners must decide whether they truly “get” their friend.  
6. **Reveal & Scoring** – The true answer is highlighted, guesses are shown, and points are awarded.  
7. **Rotation** – If nobody has reached the target score, the next player becomes Storyteller and the loop repeats.

### 1.4 Scoring Details  
| Mode      | Situation                                      | Listener Points | Storyteller Points |
|-----------|------------------------------------------------|-----------------|--------------------|
| **Simple**| Some (not all) correct                         | +Depth Mult.    | +Depth Mult.       |
|           | Everyone correct                               | +Depth Mult.    | +2 × Depth Mult.   |
| **Bluffing** | Exactly one listener correct                 | +3 × Mult.      | +3 × Mult.         |
|           | Some (not all) correct                         | +Depth Mult.    | +Depth Mult.       |
|           | Everyone correct                               | +2 × Mult.      | 0                  |
|           | Nobody correct                                 | 0               | 0 (unless trap hit)|

Depth multipliers: Narrow = 1×, Medium = 2×, Deep = 3×. In Bluffing mode, “trap hits” (listeners picking the fake answer) count as “not all correct,” rewarding the Storyteller with the listed bonus.

### 1.5 End Conditions  
- A player hits or exceeds the target score.  
- The host clicks **End game**, which immediately declares the current leaders as winners.  
- The group can also agree to stop after a fixed number of rounds; the scoreboard makes it clear who “gets” whom the most.

---

## 2. Streamlit Flow Overview

### 2.1 Entry Screen  
Single landing screen with two clear actions: **Create room** or **Join room**. The choice determines which flow is shown next; the header text changes automatically based on the route.

### 2.2 Host Flow  
1. **Host name** – Simple input; validation ensures a non-empty value.  
2. **Room name** – If the name already exists, the host sees the previous settings and can reuse or reconfigure.  
3. **Theme mode** – Radio buttons for Static vs Dynamic. Static mode exposes multiselect suggestions plus a custom-theme text field; dynamic mode skips ahead.  
4. **Level mode** – Similar structure to theme selection. Static mode asks for Narrow/Medium/Deep; dynamic mode defaults to Narrow but lets the Storyteller override per turn later.  
5. **Lobby** – Shows overall configuration, lets the host tweak gameplay mode and max score, remove players if necessary, and finally start the session. Once started, everyone is routed into the in-game view.

### 2.3 Join Flow  
1. **Player name** – Basic text field.  
2. **Room code** – Includes validation for unknown codes and detects already-started games.  
3. **Lobby** – Mirrors the host lobby summary so players see settings, joined friends, and a reminder to wait until the host begins. Joining players can “Change room,” which removes them cleanly and returns to the code screen.

### 2.4 In-Game Flow  
The shared “Game board” is always visible and includes room details, scoreboard, current Storyteller badge, and live phase guidance. The board also displays a personalized caption (“You are playing as ___”) to prevent confusion in multi-device households.

Phases:
1. **Theme Selection** (if dynamic) – Only the Storyteller sees the controls; everyone else sees a waiting message. Static themes auto-advance using a round-robin rotation.  
2. **Level Selection** (if dynamic) – Follows the same pattern.  
3. **Question Proposal** – Automatically surfaces a question; Storyteller can edit or hit **Change question** to request a fresh prompt.  
4. **Answer Entry** – Text areas for true/trap answers with optional “Suggest…” buttons and obvious guidance on when extra input is mandatory.  
5. **Options Build** – Choices are generated immediately so the Storyteller can review them; the **Change options** button reshuffles if needed. Once confirmed, the phase switches to guessing.  
6. **Guessing** – All listeners see the question and the options. Their personal selection persists if they navigate away temporarily. The host can force a reveal if someone disconnects.  
7. **Reveal & Scoring** – Highlights which friends guessed correctly, shows trap victims, and announces point deltas.  
8. **Results** – Triggered automatically when someone wins or manually when the host ends the game. Displays an ordered scoreboard and “Return to host lobby / Back to entry” actions.

Every button is color-coded for clarity (green for “Next/Refresh,” red for “Back/Change room,” orange for AI-assisted actions, blue for “Confirm,” black for “danger” actions) and includes loading spinners during long LLM calls so users always know something is happening.

---
