# Automatic Taxonomy Evolution

## Scope

Automatic evolution applies only to Question Aspects and Question Perspectives. Levels, Named Themes, Random, and the legacy Question Angle Catalog do not change through this path.

Taxonomy evolution is versioned and slower than ordinary question enrichment. A Taxonomy Candidate is never usable by proposal agents in the run that created it.

## Core Distinction

- A **Question Aspect** names what subject or life facet the question explores.
- A **Question Perspective** names the lens used to approach an Aspect.

If a proposal changes both the subject and the lens, split it into two Taxonomy Candidates. Compound labels such as `work-conflict-memory` fail because they encode a scenario or a Theme-specific combination rather than one reusable taxon.

## What Can Trigger a Proposal

A taxonomy proposal may begin when one of these signals repeats:

- otherwise promising Creative Concepts cannot be classified under the current definitions;
- independent ontology classifiers repeatedly abstain for the same reason;
- the Human Review Queue contains a recurring classification gap;
- a coverage analysis finds a coherent region hidden inside an overly broad existing taxon;
- relation judgments repeatedly confuse two existing taxa, suggesting a merge, split, or definition repair.

One isolated unusual question is not sufficient. The supporting concepts must have been created without the proposed label and must come from separate enrichment runs or scouts, preventing the taxonomy agent from manufacturing its own evidence.

## Taxonomy Candidate Record

Every candidate contains:

```text
candidate_id
kind: aspect | perspective
proposed_name
plain_definition
inclusion_rules[]
exclusion_rules[]
positive_examples[]
counterexamples[]
closest_existing_taxa[]
explicit_differences[]
supporting_unclassified_concept_ids[]
affected_taxon_ids[]
proposed_operation: add | alias | merge | split | rename | deprecate
provenance
```

Names must be concise, ordinary English, and neutral across Named Themes. Definitions, not labels, determine classification.

## Stricter Evaluation Path

### 1. Support Check

The candidate must explain a reusable pattern rather than a single prompt.

- A new Aspect initially needs at least six independently created supporting concepts spanning at least three Semantic Scenarios, two Perspectives, and two Answer Spaces.
- A new Perspective initially needs at least six independently created supporting concepts spanning at least three Aspects and three Semantic Scenarios.

These are conservative starting defaults, stored in the taxonomy-policy version and changed only through audited calibration. Near-duplicate concepts count once.

### 2. Existing-Taxonomy Retrieval

Retrieve the closest names, definitions, examples, and exclusions from the entire current taxonomy. Retrieval supplies possible conflicts but does not decide synonymy.

### 3. Independent Specialist Checks

Run isolated judgments for:

- **kind correctness**: Aspect versus Perspective is stable;
- **distinctness**: the definition is not a synonym, narrower wording, or trivial combination of existing taxa;
- **reusability**: the term applies across the required diversity of examples;
- **classification clarity**: independent classifiers can apply the definition consistently to shuffled positive and negative examples;
- **variety value**: adding the term reveals a meaningful coverage region rather than only increasing label count;
- **safety and neutrality**: the term does not encode harmful assumptions or depend on a Named Theme.

Preserve independent evidence before the challenge stage, exactly as for question evaluation.

### 4. Adversarial Challenge

Ask a separate challenger to:

- classify every supporting example using only existing taxa;
- find a shorter or more general existing definition that absorbs the candidate;
- find counterexamples that make the new definition overlap ambiguously;
- test whether the proposed Perspective is really an Aspect, Scenario, Answer Space, or Wording Pattern;
- test whether the proposed Aspect is really a Theme or Scenario;
- detect whether the support set was produced by one model pattern or one enrichment run.

An unresolved challenge prevents automatic acceptance.

### 5. Shadow Classification

Before release, independent classifiers apply the candidate definition to a mixed set of supporting concepts, current bank questions, neighboring-taxon examples, and counterexamples. Taxon names are shuffled or hidden where practical so the label itself does not steer the result.

The candidate passes only if it improves stable classification without pulling unrelated questions into the new term or collapsing existing variety.

## Automatic Outcomes

The rule-based taxonomy decider produces one of these outcomes:

- **Add** a genuinely distinct Aspect or Perspective as Staged in a new taxonomy version.
- **Map to existing** when the candidate is an alias or narrower wording; retain the alias for future detection without creating a new active taxon.
- **Apply existing-taxon change** to stage a clear rename, merge, split, or deprecation in a new Taxonomy Version after every affected Question Revision has a clear reclassification plan.
- **Reject** when support, distinction, usefulness, or safety clearly fails.
- **Human review** when specialists disagree, the support pattern is unstable, or an operation would produce ambiguous reclassification.

Merge, split, rename, and deprecate are changes to a Taxonomy Version, never in-place edits. Any uncertain affected classification prevents **Apply existing-taxon change** and produces Human review instead.

## Existing-Taxon Changes

### Rename

If only the name improves and the definition is semantically unchanged, preserve the taxon ID and create a new versioned label. Historical snapshots retain the old label.

### Merge

Create a replacement taxon ID, deprecate the old IDs in the new Taxonomy Version, and keep their names as aliases. Reclassify every affected active Question Revision before release.

### Split

Create new taxon IDs with mutually explicit inclusion and exclusion rules, deprecate the broad old ID, and reclassify every affected active Question Revision. Any uncertain question blocks automatic release of the split and enters human review.

### Deprecate

Stop new proposal use, record a replacement or reason, and reclassify or retire affected questions before release. Historical versions continue to resolve the old ID.

No operation silently changes an existing Question Revision. Reclassification produces a new revision or a versioned snapshot projection as defined by the bank release policy.

## Anti-Self-Reinforcement Rules

- Taxonomy Candidates cannot seed proposal generation until released.
- Supporting concepts generated from the candidate name or definition do not count as evidence.
- Near-duplicate support counts once.
- Evidence must cross independent scouts or enrichment runs.
- Evaluation uses shuffled examples and explicit negatives.
- Taxonomy proposal agents cannot make taxonomy decisions.
- A new taxon begins with no coverage target; observed independent use must establish its value before the pipeline tries to fill it aggressively.
- If a new term quickly captures an excessive share of new concepts, pause it and challenge its definition for over-breadth.

## Version and Audit Requirements

Retain the candidate, supporting evidence, independent judgments, challenge results, affected-question set, decision reason, previous Taxonomy Version, and resulting Taxonomy Version. A taxonomy release must pass Reference Example regression checks and re-evaluate every affected Question Revision before it can be used by normal enrichment.

## Consequences

- The taxonomy can grow without routine human naming work.
- New labels explain independently observed variety instead of manufacturing it.
- Synonyms become aliases rather than duplicate active taxa.
- High-impact merges and splits remain automatic only when every affected classification is clear; ambiguity is concentrated in human review.
