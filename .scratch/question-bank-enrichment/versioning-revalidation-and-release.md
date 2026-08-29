# Question Bank Versioning, Revalidation, and Release

## Release Unit

The Question Enrichment Pipeline may run continuously, but consumers only receive immutable Question Bank Snapshots. Staged questions, unresolved review cases, partial index builds, and in-progress taxonomy changes are never visible through a released snapshot.

Each snapshot has:

- a monotonically increasing human-readable release number such as `bank-v42`;
- a content hash over its canonical manifest;
- an immutable creation timestamp;
- an exact ordered set of Question Revision IDs;
- one Taxonomy Version and Coverage Plan;
- lifecycle decisions applied by the snapshot;
- all derived index and coverage-projection versions;
- the quality, safety, admission, and evaluation-policy versions used to trust it;
- links to revalidation runs, Reference Example results, and required human spot checks;
- the previous released snapshot ID.

The content hash, not the friendly number, proves identity. Snapshot manifests and contained revisions are append-only.

## Reproducibility Contract

Reproducibility means reconstructing what inputs, evidence, versions, and rules produced a decision. It does not promise that a nondeterministic model will generate the same words again.

For every enrichment and revalidation run, retain:

- exact input proposal and bank snapshot ID;
- model provider, requested and reported model identity, parameters, and seed where supported;
- prompt template, rubric, output schema, and tool versions or hashes;
- taxonomy, coverage, source-policy, and admission-policy versions;
- all raw structured outputs allowed by the evidence policy;
- retries, errors, timestamps, and idempotency keys;
- final reason codes and decision rule version;
- semantic-index build identity and candidate-neighbor set.

Provider aliases alone are insufficient model identity. If the provider cannot expose a stable underlying revision, record the alias, timestamp, response metadata, complete input, and complete structured output so the historical decision remains auditable.

## Release Pipeline

### 1. Freeze a Candidate Manifest

Select the staged accepted revisions, intended current revisions, retirements, Taxonomy Version, and Coverage Plan. Assign a candidate ID. Further enrichment creates a later candidate rather than mutating this one.

### 2. Validate Trusted Records

Check referential integrity, immutable revision chains, one current revision per Question ID, allowed lifecycle transitions, complete Question Provenance, valid source permission, exactly one Level, approved taxonomy references, and zero-to-many Named Theme memberships without Random.

### 3. Rebuild Derived Projections

Build lexical and vector indexes, semantic fingerprints, neighbor sets, coverage projections, and release reports from the frozen manifest. Rebuilding from canonical records must produce the same logical projection for a given projection version.

### 4. Revalidate the Required Scope

Run Reference Example regression checks first. Then apply the change-scope table below. Store new Evaluation Evidence without overwriting earlier evidence.

### 5. Apply Release Gates

The candidate must satisfy every gate below. A failed gate holds the candidate and leaves the current snapshot unchanged.

### 6. Publish Atomically

Persist the immutable manifest and all verified projection references, then atomically change the `current_snapshot_id` pointer. Consumers either see the complete previous release or the complete new release.

## Revalidation Scope

| Change | Minimum revalidation scope |
|---|---|
| New question or any canonical-text edit | Full quality, Level, safety, ontology, provenance, and whole-bank relation evaluation for that revision |
| Question Provenance or source-rights change | Every Question Revision sharing the affected ancestry |
| Theme Membership classifier or Named Theme definition change | Reclassify affected questions and recompute affected Coverage Regions; question admission quality is unchanged |
| Aspect or Perspective rename with unchanged definition | Referential and example regression checks; no semantic question re-evaluation |
| Aspect/Perspective definition change, merge, split, or deprecation | Every affected question plus neighboring-taxon counterexamples and all affected coverage projections |
| Wording, scenario, answer-space, embedding, retrieval, or semantic-repeat logic change | Rebuild neighbors for the entire candidate snapshot and rerun relation judgments for changed neighbor sets |
| Quality, Level, safety, Bounded Openness, or admission-rule change | Reference Examples, then every active and staged Question Revision affected by the changed rule; use the whole bank if scope cannot be proven |
| Proposal prompt, evaluator prompt, rubric, or model change with unchanged rule | Reference Examples plus a representative stratified audit of evaluator changes; re-evaluate generated proposals for proposal changes; expand to every affected revision if results differ materially or scope cannot be proven |
| Coverage Plan or completion threshold change | Recompute all coverage projections and completion status; question trust is unchanged unless taxonomy or quality definitions also changed |
| Storage-only or projection-performance change | Interface contract, migration integrity, and projection equivalence checks; no LLM re-evaluation |

When scope is uncertain, choose the broader scope. Revalidation may retire or hold a revision for the new candidate snapshot without altering the status of older immutable snapshots.

## Release Gates

A candidate releases only when:

- every included revision is either a retained Active revision or a selected Staged revision eligible to become Active, and is covered by final Accept authority;
- no included evidence is missing, unresolved, or attached to different text;
- provenance and permission checks pass;
- Reference Examples meet the current expected outcomes;
- no prohibited semantic repeat remains in the candidate snapshot;
- every affected taxonomy classification is resolved;
- every Named Theme × Level horizon required by the current Coverage Plan remains healthy;
- completion status is correctly recalculated, whether complete or still growing;
- all indexes and derived projections verify against the manifest;
- the release report contains no unresolved critical failure;
- the required ten-question human spot check for the first release or a major policy change has passed.

A non-empty Human Review Queue does not block unrelated releases. Queued proposals simply cannot appear in the candidate manifest.

## What Counts as a Major Change

Require the post-change ten-question human spot check when any of these changes:

- quality or safety contract;
- admission decision rules;
- semantic-repeat relation rules;
- Aspect/Perspective meaning through merge, split, or material definition change;
- evaluator topology;
- a material change to a production proposal or evaluator prompt or rubric;
- the production proposal or evaluation model family or material model configuration;
- source-permission policy.

Pure storage, performance, formatting, or label-only changes do not require human review if automated equivalence checks pass.

If the spot check finds a meaningful recurring defect, hold the candidate, diagnose and repair the affected evaluator or policy, revalidate the affected scope, and run another ten-question check as already defined by the human audit contract.

## Rollback and Withdrawal

Rollback atomically moves `current_snapshot_id` to a previously released, still-trusted snapshot. It does not edit or delete the failed release.

If a safety, consent, or rights issue makes an old snapshot unsafe to use:

1. mark it Withdrawn in an append-only release-status record;
2. select the latest earlier safe snapshot or build an emergency candidate excluding the affected revisions;
3. prevent consumers from selecting the withdrawn snapshot by default;
4. preserve its manifest and non-restricted audit history.

A rolled-back candidate may be corrected only by producing a new snapshot with a new identity.

## Trust for Later Gameplay Integration

A snapshot is trusted for future gameplay work when it is Released, not Withdrawn, its content hash verifies, every release gate passed under the manifest's recorded versions, and the integration can pin that exact snapshot rather than reading mutable staging data. Runtime selection policy remains a separate later design.

## Consequences

- Continuous autonomous enrichment cannot leak partial or newly regressed content.
- Every live corpus can be reconstructed and audited even when model execution is nondeterministic.
- Changes revalidate the narrowest provable affected scope, with whole-bank fallback when uncertainty remains.
- Rollback is fast, atomic, and does not destroy evidence.
