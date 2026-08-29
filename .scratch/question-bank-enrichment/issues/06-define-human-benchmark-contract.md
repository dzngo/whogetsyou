# Define the Human Benchmark and Audit Contract

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 04

## Question

What human-labelled evidence must ground and periodically audit the otherwise automatic Question Enrichment Pipeline? Decide the benchmark unit, coverage across Theme and Level, diversity and edge-case composition, reviewer instructions and agreement, holdout policy, acceptance thresholds, audit cadence, and what failures force recalibration or stop automatic admission.

## Answer

The deliberately lightweight process is recorded in [`human-calibration-and-spot-checks.md`](../human-calibration-and-spot-checks.md).

Agents prepare about thirty good, bad, repetitive, distinct, Shallow, Deep, and boundary Reference Examples; one human domain expert confirms or corrects them once. The historical eval corpus remains excluded. Clear proposals are admitted or rejected automatically, uncertain cases go to the Human Review Queue, and the human occasionally spot-checks ten accepted questions.

A meaningful failure holds the affected batch out of the trusted bank while agents diagnose, revise, and recheck it. There is no routine second reviewer, per-question approval, hidden statistical partition, or complex target at this stage; the system adds stronger measurement only if the simple process proves unreliable.
