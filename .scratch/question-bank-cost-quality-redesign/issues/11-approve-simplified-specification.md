# Approve the Simplified Question Enrichment Specification

Type: prototype
Label: wayfinder:prototype
Status: resolved
Assignee: root
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Define Migration from the Existing Enrichment System](10-define-redesign-migration.md)

## Question

Does the consolidated redesign specification faithfully combine every resolved cost, creativity, evaluation, repetition, metadata, human-review, release, pilot, and migration decision into a simpler implementation contract that can meet the $2 target without weakening the Question Quality Floor?

## Prototype for approval

- Normative contract: [`../implementation-specification.md`](../implementation-specification.md)
- Interactive state-model demo: branch `codex/prototype-simplified-pipeline-contract`, commit `82204f9`

The specification traces every contract area to resolved tickets 01–10. The throwaway HTML prototype makes the hard-to-reason-about rules visible without persistence or provider calls: a genuinely passing `$0.20` pilot, retained Unknown Spend with no automatic retry, semantic pair overflow, protected human review, one-cent unit economics, provider-free verification, and whole-release blocking after a sampled defect.

Offline verification completed before approval:

- the prototype JavaScript parses successfully;
- its passing-pilot walkthrough reaches `may request production authorization` only after every required stage and four protected checks;
- its ambiguous-failure walkthrough retains the creative reservation, sends no retry, and creates no proposals;
- its 200-question walkthrough verifies without increasing provider attempts;
- every local link in the consolidated specification resolves; and
- `git diff --check` passes.

The prototype is not production code. After approval it will be captured on a throwaway prototype branch and removed from the implementation branch; the approved specification and ticket verdict remain as the implementation source of truth.

## Answer

Approved by the user on 2026-09-02.

[`../implementation-specification.md`](../implementation-specification.md) is the authoritative implementation contract for Question Bank Enrichment v2. It faithfully combines resolved tickets 01–10, retains the complete Question Quality Floor, makes the Gemini/GPT multi-agent roles explicit, and replaces the rejected Coverage Plan and per-question fan-out topology with bounded batches and deterministic authority.

The state-model prototype confirmed that the proposed contracts compose coherently:

- a successful pilot can complete every mandatory stage below both `$0.20` exposure and `$0.01` per accepted question;
- an ambiguous provider failure retains Unknown Spend and cannot retry itself;
- semantic pair overflow blocks rather than sampling away evidence;
- metadata occurs after staging and cannot revoke admission;
- human defects block scale or release rather than being deleted around; and
- release verification can complete without increasing provider attempts.

The throwaway prototype is preserved on branch `codex/prototype-simplified-pipeline-contract` at commit `82204f9` and is absent from the implementation branch. The approved specification, this verdict, and the traceability table remain on the implementation branch.
