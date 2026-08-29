# Define Bank Versioning, Revalidation, and Release

Type: grilling
Status: resolved
Blocked by: 06, 08, 09, 10, 11, 12

## Question

How are Question Bank snapshots versioned, audited, re-evaluated, and released as prompts, models, rubrics, taxonomies, or individual questions change? Define reproducibility evidence, regression gates, invalidation scope, rollback, and the conditions under which a bank version is trusted for later gameplay integration.

## Answer

Continuously enriched questions remain Staged until an immutable `bank-vN` manifest with a content hash freezes exact Question Revisions, Taxonomy Version, Coverage Plan, policies, evidence, and derived indexes. Reproducibility preserves exact inputs, structured outputs, model/prompt/rubric versions, and decision rules rather than promising deterministic regeneration. A change-scope table requires full re-evaluation for text and quality changes, targeted reclassification for taxonomy changes, and whole-bank neighbor rebuilding for semantic detection changes. Reference Examples, integrity, provenance, repetition, taxonomy, coverage, index, and required spot-check gates—including after material production prompt or rubric changes—must pass before an atomic current-snapshot pointer update. Rollback selects a prior immutable snapshot; unsafe releases are marked Withdrawn rather than edited.

## Comments

- Decision record: [`../versioning-revalidation-and-release.md`](../versioning-revalidation-and-release.md)
