# Use Canonical English For AI-Generated Content

We generate AI-created questions and suggested answers in English, then translate player-facing text into the room language with a fixed low-latency translation model. This keeps prompt inputs and question history consistent while still showing players natural text in their chosen language; player-submitted final answers remain in the room language.

**Consequences**

- Question state stores both a Canonical Question and a Display Question.
- Non-English rooms pay one translation call for generated questions and suggested answers.
- Storyteller edits to non-English Display Questions are translated back to English when confirmed.
- The separate question refinement step is removed; translation handles natural player-facing phrasing when needed.
