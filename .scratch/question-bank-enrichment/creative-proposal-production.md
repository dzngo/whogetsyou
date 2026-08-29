# Creative Proposal Production

## Goal

Produce genuinely different question proposals without allowing agents to converge on paraphrases before the evaluation pipeline begins.

The proposal system is fully automatic. It creates structured Creative Concepts before it creates question wording.

## Creative brief

The orchestrator starts one proposal batch with:

- exactly one Level;
- the approved diversity ontology and its version;
- current coverage gaps expressed as needed Aspects, Scenarios, Perspectives, or Answer Spaces;
- compact fingerprints describing occupied bank regions without exposing full question text;
- the active source and provenance policy.

Theme is absent from the brief. Theme Membership is classified after global comparison under the Question Quality Contract.

## Independent scouts

Four specialized scouts work independently:

- **Aspect Scout** explores underrepresented subjects or life facets.
- **Scenario Scout** invents realistic concrete situations.
- **Perspective Scout** applies different lenses to otherwise ordinary material.
- **Contrast Scout** searches for neglected trade-offs, boundaries, tolerances, and reversals.

Each scout produces Creative Concepts containing proposed Question Aspect, Semantic Scenario, Question Perspective, Answer Space, and a short explanation of what makes the concept different.

Scouts do not see:

- other scouts' concepts before reveal;
- full Question Bank text;
- Reference Examples as wording inspiration;
- proposal-agent identities or outputs from earlier runs beyond compact coverage and novelty fingerprints.

This independence barrier prevents first-idea anchoring and correlated paraphrases.

## Concept comparison before wording

After all scouts finish, a concept-comparison stage evaluates overlap using the approved Diversity Ontology. Overlapping concepts are rejected or merged before a composer spends effort on wording.

Sharing only an Aspect or Perspective is allowed. Concepts whose Scenario, Perspective, and Answer Space substantially coincide are repeat candidates and do not both advance.

The comparison retains the rejected concept and its evidence in Question Provenance so later agents do not continually rediscover it.

## Composition

One composer turns each surviving Creative Concept into one English question. The composer may improve naturalness and Bounded Openness but may not silently replace the concept's facets.

After composition, each question receives a global bank-neighbor screen. This catches wording or meaning collisions that were not visible at concept level.

Questions that survive are handed to the separate automated evaluation topology with complete provenance. Proposal agents never judge their own admission.

## Taxonomy expansion path

Scouts may propose a new Question Aspect or Question Perspective when the existing ontology cannot represent a useful concept. That output is a taxonomy proposal, not a bank question.

Question composition stops until **Define Automatic Taxonomy Evolution** approves, merges, or rejects the proposed taxonomy entry. Unapproved taxonomy may not be used to populate the trusted bank.

## Failure behavior

Shared brainstorming before independent exploration is prohibited. The prototype demonstrates that sharing the first idea causes scouts to converge on the same Aspect, Scenario, and Answer Space with superficial Perspective variation.

If concept comparison rejects most of a batch, the orchestrator creates a new brief targeting different coverage regions rather than asking agents to paraphrase the survivors.

## Prototype evidence

The decision was validated through the interactive logic prototype on branch `codex/prototype-creative-proposal-production`, commit `efdd918`, at `prototypes/creative_proposal_factory.html`.
