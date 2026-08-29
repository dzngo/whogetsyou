# Question Source and Provenance Policy

## Allowed sources

Question Bank proposals may originate from:

- de novo generation by the Question Enrichment Pipeline;
- project-authored prompts, taxonomies, rubrics, and examples;
- human-authored questions explicitly contributed for this project;
- external questions only when reuse rights are explicit, compatible, and retained as provenance evidence.

Human authorship establishes source rights, not quality. Every proposal passes the same automatic quality, diversity, and admission pipeline.

## Prohibited or excluded sources

The pipeline must not scrape, copy, or silently ingest an external question collection.

Existing gameplay questions and Storyteller edits are excluded from bank creation because current records lack consent, authorship, and complete transformation history. Question Usage Metrics also do not make gameplay text eligible as source material.

The existing eval corpus is ignored completely. It is not a bank source, benchmark seed, negative-example collection, or calibration dataset. The future human benchmark must be created specifically for the approved Question Bank contracts.

Unlicensed external text must never be placed in proposal-agent context as inspiration. A paraphrase does not erase its source obligations.

## Ownership posture

Question Bank contents are private project content by default. Publication, sale, open licensing, or redistribution requires a separate deliberate decision.

Every non-project source requires explicit compatible rights and retained evidence. When rights are unclear, the source is prohibited rather than sent to the Human Review Queue.

## Question Provenance

Every proposal and rewrite preserves immutable ancestry. Provenance must be sufficient to reconstruct where the text came from and which transformations produced the current form.

Required provenance concepts include:

- source type and stable source identifier or content hash;
- author, contributing agent, or generating system identity;
- model and provider version where applicable;
- prompt, rubric, taxonomy, and pipeline version;
- creation timestamp and run identity;
- parent proposal or transformation inputs;
- applicable license, ownership, or consent evidence.

The exact storage schema, identifiers, and lifecycle behavior belong to **Define the Question Bank Record and Lifecycle**.

## Benchmark isolation

Reference Examples and their confirmed outcomes are not source material. Proposal agents must never receive them in generation context.

Evaluator configurations may be checked against the Reference Examples, with the expected outcome applied by the scorer after the evaluator has produced its structured judgment. No second, separately managed benchmark set is required at this stage.

## Current-repository consequence

The current room store, feedback sheet, and historical eval JSONL files do not contain sufficient provenance to feed the Question Bank. They remain outside the Question Enrichment Pipeline unless a future explicit policy replaces this decision.
