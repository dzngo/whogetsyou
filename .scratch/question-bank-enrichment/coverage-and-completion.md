# Coverage and Bank Completion

## Coverage Model

The bank must cover every existing Named Theme × Level horizon while preserving global variety. It must not attempt to populate every mathematically possible taxonomy combination.

A **Coverage Region** is:

```text
Named Theme + Level + Question Aspect + Question Perspective
```

Semantic Scenario, Answer Space, and Wording Pattern measure internal variety inside a region. They are not additional axes to multiply into a combinatorial target.

Random has no Coverage Regions because it is a wildcard, not a Theme Membership.

## Coverage Plan

Each Taxonomy Version has a versioned Coverage Plan. For every possible region, the plan records one of:

- **Required**: the combination is natural and important enough to maintain.
- **Exploratory**: the combination may produce useful questions but is not necessary for completion.
- **Invalid**: the combination is misleading, unsafe, incoherent, or not meaningfully connected to the Named Theme.

Independent classifiers propose region status from the Theme, Level, Aspect, and Perspective definitions. A challenger tries to show that Required combinations are artificial and that Invalid combinations have plausible examples. Material disagreement enters the Human Review Queue. The plan is released with the Taxonomy Version rather than inferred from whatever the generator has already happened to create.

This prevents existing bank concentration from declaring itself complete and prevents a full Cartesian-product explosion.

## Question Contribution

- One active Question Revision contributes to every Named Theme in its Theme Memberships at its one Level.
- It counts once in the global Question Bank even if it contributes to several Theme horizons.
- A question contributes to one Aspect and one Perspective region per Theme Membership.
- Multi-theme classification is performed independently from coverage pressure. Agents may not add extra memberships merely to fill gaps.
- Retired and Staged questions do not count toward released coverage.

## Healthy Depth

A Required Coverage Region is healthy when it contains at least three active questions whose Semantic Scenarios are meaningfully different and whose Answer Spaces are not all the same.

Three is the initial minimum because:

- one question demonstrates presence, not variety;
- two questions demonstrate only one contrast;
- three distinct scenarios show that the region can support repeatable breadth.

The minimum is a versioned starting policy, not a permanent truth. Reference Examples, audits, and later sampling requirements may raise it. Near-duplicates never count as separate depth.

A Named Theme × Level horizon is healthy when:

- every Required region meets its depth floor;
- no unresolved Aspect Repetition alert remains;
- no single Wording Pattern or Answer Space dominates merely because proposal agents repeat an easy template;
- Deep regions contain questions that reveal characteristic personal information, not only generic reflection;
- the latest spot check found no recurring quality defect that would hold the batch.

The system reports counts and concentration distributions, but no raw total alone can make a horizon healthy.

## Gap Priority

Choose enrichment briefs in this order:

1. an unhealthy Named Theme × Level horizon;
2. a missing Required region;
3. a Required region below three distinct Semantic Scenarios;
4. a region with narrow Answer Space or Wording Pattern concentration;
5. an Exploratory region that independent scouts repeatedly discover;
6. open discovery for a new valid Aspect, Perspective, or region.

Within the same priority, rotate across Themes, Levels, Aspects, and Perspectives rather than repeatedly targeting the easiest area. Coverage pressure supplies only Level, ontology definitions, gap descriptions, and compact bank fingerprints to proposal scouts; it does not show Theme or full questions during creative concept formation.

## Coverage Measurements

For each released snapshot, compute:

- active unique Question IDs and exact Question Revisions;
- counts by Named Theme × Level;
- Required, healthy, under-depth, Exploratory, and Invalid-region counts;
- distinct Semantic Scenario families per region;
- Answer Space and Wording Pattern concentration per region and horizon;
- Aspect and Perspective concentration globally and per horizon;
- semantic-neighbor density and unresolved repetition alerts;
- proposal, acceptance, rejection, and human-review counts by targeted gap;
- reasons distinct proposals fail, especially semantic-repeat versus quality failures.

These are derived projections. They can be rebuilt from a Question Bank Snapshot, Taxonomy Version, Coverage Plan, and enrichment-run records.

## Diminishing-Returns Challenge

Once every Named Theme × Level horizon is healthy, run a completion challenge instead of stopping immediately:

1. Run three independent discovery rounds.
2. Each round uses at least two independently configured proposal strategies, and each strategy creates at least twenty Creative Concepts.
3. Within every strategy, half target the currently thinnest regions and half perform open discovery without a proposed new taxon.
4. Evaluate every resulting question through the normal pipeline.
5. A round is saturated only when every individual strategy and the round overall convert fewer than five percent of concepts into accepted globally distinct questions, and no strategy discovers a new valid Coverage Region.

The bank is **Enrichment-complete for that version** only when all horizons remain healthy and all three rounds are saturated. The three rounds, twenty concepts per strategy, two-strategy minimum, and five-percent defaults are explicit, versioned starting thresholds. They must be recalibrated if proposal models, creativity prompts, taxonomy, or later sampling needs materially change.

Low yield caused by poor wording, safety failures, outages, or a weak proposal agent does not count as saturation. The dominant rejection reason must be genuine semantic or coverage redundancy, and the challenger must test at least two proposal strategies to reduce model-specific false completion.

## Completion Is Versioned, Not Final

Completion applies to a specific combination of:

- Question Bank Snapshot;
- Taxonomy Version and Coverage Plan;
- quality rubric and Evaluation Topology version;
- proposal strategies used in the completion challenge.

A taxonomy change, material quality-rule change, repeated audit defect, or demonstrably stronger proposal strategy reopens the affected regions. Ordinary new model releases do not automatically invalidate completion unless the configured production pipeline changes or a challenge shows meaningful new yield.

## What Completion Does Not Mean

- It does not authorize gameplay sampling or ranking; that remains a later design.
- It does not claim that no more good questions exist.
- It does not require every Exploratory region to be populated.
- It does not let usage metrics change bank contents or coverage priority in this effort.
- It does not reward broad Theme tagging or cosmetic paraphrases.

## Consequences

- The final bank size emerges from meaningful coverage and distinctness rather than a vanity target.
- Every Named Theme × Level horizon receives repeatable internal variety.
- Completion can be challenged and reopened without discarding prior snapshots.
- A weak generator cannot easily masquerade as corpus saturation.
