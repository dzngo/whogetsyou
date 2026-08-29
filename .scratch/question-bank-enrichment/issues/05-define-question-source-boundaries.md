# Define Question Source and Provenance Boundaries

Type: grilling
Status: resolved

## Question

Which sources may the Question Enrichment Pipeline use to create questions—de novo generation, existing game questions, rejected or edited internal questions, human-authored seeds, or external question collections—and what provenance, transformation, licensing, and contamination boundaries must apply before any output can enter the Question Bank?

## Answer

The approved policy is recorded in [`question-source-and-provenance-policy.md`](../question-source-and-provenance-policy.md).

The pipeline may use de novo agent generation, project-authored guidance, explicitly contributed human questions, and external questions with explicit compatible reuse rights. No human-authored proposal bypasses evaluation. External collections may not be scraped or silently ingested, and unlicensed text may not be supplied as inspiration.

Existing gameplay questions, Storyteller edits, and the entire existing eval corpus are excluded from bank creation and benchmark construction. The new benchmark must be purpose-built. Every allowed proposal and rewrite retains immutable Question Provenance, benchmark content remains isolated from proposal agents, and bank contents are private project content unless deliberately licensed otherwise.
