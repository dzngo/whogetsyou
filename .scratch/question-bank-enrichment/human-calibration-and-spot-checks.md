# Human Calibration and Spot Checks

## Goal

The Question Enrichment Pipeline should build the Question Bank with as little human involvement as practical. Humans align the system and inspect its work; they do not approve every question.

## Reference Examples

Create about thirty purpose-built examples covering:

- good and bad Shallow questions;
- good and bad Deep questions;
- obvious and subtle semantic repetition;
- questions that share only an Aspect or Perspective and should remain distinct;
- important safety and Bounded Openness boundaries.

Agents prepare the examples and proposed labels. One human domain expert confirms or corrects them once. Written explanations are required only when correcting an agent or when the intended rule is unclear.

These examples replace the excluded historical eval corpus. They align the evaluators but are never supplied to proposal agents as text to imitate.

## Automatic operation

After alignment:

1. Proposal agents create questions automatically.
2. Evaluation agents apply the approved quality and diversity contracts.
3. Clear decisions are admitted or rejected automatically.
4. Questions the agents cannot decide go to the Human Review Queue with their evidence and disagreement.

The mature goal is for almost all proposals to be handled without human review.

## Spot checks

The human occasionally inspects ten randomly selected accepted questions. Always perform a spot check for the first automatically built batch and after a major change to models, prompts, rubrics, taxonomy, or agent flow.

If the sample reveals a meaningful quality, safety, or repetition problem:

- hold the affected batch out of the trusted bank;
- have agents recheck the batch;
- diagnose and revise the responsible rules or agent configuration;
- run another ten-question spot check before trusting the revised batch.

No second reviewer, fixed percentage target, hidden statistical partition, or per-question approval is required at this stage. Add stronger measurement only if simple spot checks prove insufficient.
