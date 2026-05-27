# Question Review Evals Context

This context defines the lightweight question-quality review tool for "Who Gets You?". The eval tool exists to speed up prompt iteration without running a full multiplayer game.

## Language

**Question Review Harness**:
A separate internal tool for generating and reviewing AI-produced questions outside the player-facing game. It is for human judgment, not deterministic automated testing.
_Avoid_: Unit test, game simulation

**Review Sample**:
One generated question plus its generation metadata, such as model, language, theme, level, sample ID, Canonical Review Text, Display Review Text, and the exact generation and translation prompt payloads. A Review Sample is read-only during review so ratings describe the raw generated output.
_Avoid_: Editable draft

**Candidate Set Review**:
A human review of a ranked Candidate Set. Unlike gameplay, the review harness shows the full Candidate Set so reviewers can judge candidate quality, angle diversity, and whether the top-ranked candidate is actually strongest.
_Avoid_: Gameplay preview

**Canonical Review Text**:
The English question generated for a Review Sample before translation. It is saved so reviewers can distinguish generation problems from translation problems.
_Avoid_: Source output

**Display Review Text**:
The translated question shown to reviewers. Reviewers judge this text because it matches what players will see.
_Avoid_: Localized output

**Translation Trace**:
The translation model and prompt payload used to produce Display Review Text from Canonical Review Text. It is saved with reviews so translation problems can be separated from generation problems.
_Avoid_: Refinement trace

**Question Review**:
A saved human judgment for a Review Sample, including the exact generation prompt and translation trace. A Question Review requires a rating and may include preset issue tags, an Other note, and a free comment.
_Avoid_: Test result, model score

**Question Quality Success Criteria**:
The review targets used to decide whether prompt and generation changes improved question quality. Initial targets are at least 70% Fine or Very good top-ranked candidates, distinct Question Angles within a five-candidate set when enough angles exist, no single angle family above 25% in a 20-candidate review session, fewer Bad Repetitive reviews than the prior baseline, and separate tracking of Weird wording issues.
_Avoid_: Acceptance test

**Review Session**:
One Streamlit process lifetime for the review harness. A Review Session starts when `streamlit run evals/review_questions_app.py` launches, uses one local-time timestamped JSONL result file, and survives normal Streamlit reruns caused by widget interaction.
_Avoid_: Browser session, batch

**Session Result File**:
The JSONL output file for one Review Session, named with the local launch time, such as `question_reviews_20260527_143012.jsonl`. All reviews saved during that Streamlit process are appended to this file.
_Avoid_: Global result file

**Rating**:
The required overall quality judgment for a Review Sample. Valid ratings are Bad, Fine, and Very good.
_Avoid_: Pass/fail

**Preset Tag**:
A controlled issue label used to make prompt problems easier to group later. Preset Tags are Nonsense, Too serious, Too fantasy, Too childish, Not realistic, Too generic, Off theme, Too long, Weird wording, Repetitive, Not funny, Unsafe / violated, Wrong language, and Other.
_Avoid_: Free-form category

**Other Note**:
A required explanation when the Other Preset Tag is selected. It captures a new issue type without losing detail.
_Avoid_: Miscellaneous

**In-Session History**:
The list of canonical English questions already generated during the current Review Session for the same theme and level. The review harness passes this history into later generations across batches to test anti-repetition behavior, even when generated samples have not been reviewed.
_Avoid_: Persistent history

**Prompt Inspection**:
A no-LLM mode that displays the exact system and user prompt payload that would be sent for a chosen theme, level, and language.
_Avoid_: Dry generation

**Question Latency Run**:
A CLI benchmark of the production question generation prompt chain. It measures canonical English generation latency, optional translation latency, and total latency per model/theme/level sample. Results are written as JSONL records under `evals/results/` and summarized in the terminal.
_Avoid_: Load test, quality review

## Latency Script

Run the latency benchmark with:

```bash
uv run python evals/question_latency_analysis.py --models gemini-2.5-flash gpt-4o-mini --themes "Random 🎲" --levels shallow deep --count 5
```

For model-list analysis, put one model per line in a text file:

```text
gemini-2.5-flash
gpt-4o-mini
# comments and blank lines are ignored
```

Then run:

```bash
uv run python evals/question_latency_analysis.py --models-file evals/models.txt --themes "Random 🎲" --levels shallow deep --count 5
```

Use English language runs to measure generation only, and non-English language runs to include translation. Use `--delay-seconds` if provider rate limits affect a run.

## Example Dialogue

Developer: "Should question evals live in the automated tests folder?"

Domain expert: "No. This is a human review harness that calls an LLM and produces subjective ratings, so it belongs in evals."

Developer: "Should reviewers edit generated questions before rating?"

Domain expert: "No. They should rate the raw generated question and explain problems with tags or comments."

Developer: "Should every generated question be saved?"

Domain expert: "No. Save only reviewed samples, because rating and feedback are the useful artifacts."

Developer: "Should saved reviews include the prompt?"

Domain expert: "Yes. Save the generation prompt and translation trace, because reviewers judge translated display text."
