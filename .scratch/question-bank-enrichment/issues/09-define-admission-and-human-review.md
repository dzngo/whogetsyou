# Define Admission Decisions and the Human Review Queue

Type: grilling
Status: resolved
Blocked by: 06, 07, 08

## Question

Given the approved quality evidence and agent topology, what exact evidence is sufficient to admit, reject, quarantine, or send a proposed question to the Human Review Queue? Define uncertainty and disagreement, the information retained for reviewers, human resolution outcomes, retry limits, and the fail-closed rules that prevent questionable proposals entering the Question Bank.

## Answer

Use exactly three Admission Outcomes: Accept, Reject, and Human review; a separate quarantine state is unnecessary. Acceptance requires complete passing evidence and global distinctness. Clear critical failures reject. Any material uncertainty, conflict, missing evidence after one execution retry, unfamiliar failure pattern, or taxonomy dependency enters the Human Review Queue with a concise evidence packet. Reviewers may append a human Accept or Reject outcome, edit into a fully re-evaluated proposal version, or hold for taxonomy/rubric repair; the original automatic abstention remains immutable. The same review module owns uncertain post-accept Theme classification, which must resolve before bank identity is created. Automatic rewriting of rejected proposals is forbidden; the creative system explores a new concept instead. Missing evidence and write failures always fail closed.

## Comments

- Decision record: [`../admission-and-human-review.md`](../admission-and-human-review.md)
