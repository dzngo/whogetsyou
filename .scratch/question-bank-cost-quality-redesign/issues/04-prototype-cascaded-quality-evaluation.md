# Prototype Cascaded Quality Evaluation

Type: prototype
Label: wayfinder:prototype
Status: resolved
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Define the Enrichment Budget and Cost Ledger](02-define-enrichment-budget-contract.md)

## Question

What deterministic checks, batched normal GPT evaluation, uncertainty criteria, and selective high-reasoning escalation preserve the complete Question Quality Floor with the fewest provider calls? Define structured evidence, batch-isolation risks, automatic rejection, and when a second evaluator can materially change the result.

## Answer

Use a three-stage quality cascade for each 20-question creative batch:

1. **Deterministic preflight** makes no provider call. It rejects malformed question text, an invalid Level or provenance/source contract, and normalized exact duplicates within the batch or trusted bank. It may flag suspicious text, but it cannot declare semantic safety, Level fit, or Deep revelation from keywords.
2. **Two isolated normal-reasoning GPT batches of ten** evaluate every surviving question once. Use `gpt-5.4-mini` at medium reasoning with a finite input cap of 4,500 tokens and `max_output_tokens=3,000` per call.
3. **At most one selective high-reasoning GPT batch** re-evaluates only questions whose first evidence contains uncertainty. It sees the question, expected Level, and rubric—not the first evaluator's verdict—and uses at most 4,000 input tokens and 7,000 reasoning-inclusive output tokens.

Each ordinary batch is formed by a stable interleave of the four creative source batches, but the evaluator sees neither strategy labels nor sibling provenance. It judges each item independently; the prompt forbids rankings, quotas, comparisons, and using one candidate as evidence about another. A response must contain exactly one schema-valid record for every requested candidate ID. Missing, duplicated, or unknown IDs invalidate that response, produce no trusted passes for the batch, and do not trigger an automatic retry.

### Required evidence

Each candidate record contains:

- candidate ID, expected Level, stage, model/prompt/policy versions, and invocation ID;
- `clarity`, `answerability`, `emotional_safety`, `level_fit`, and `deep_revelation`, each exactly `pass`, `fail`, or `uncertain` (`deep_revelation` is `not_applicable` only for Shallow);
- an overall `pass`, `reject`, or `uncertain` result derived from the rubric fields;
- bounded reason codes and concise evidence without private chain-of-thought.

The deterministic resolver—not the model—applies the outcome rule. Any definitive required-field failure is an automatic quality rejection. All applicable fields passing yields `quality_pass`, which still awaits the semantic-repetition gate and is not an Admission Outcome. Any uncertainty, missing field, malformed evidence, or execution ambiguity can never become a pass by default.

The high-reasoning evaluator can materially change only an uncertain first result: all passes become `quality_pass`, any definitive failure becomes Reject, and remaining uncertainty becomes eligible for bounded Human Review. It never reopens an ordinary evaluator's definitive pass or failure merely to manufacture consensus. More than six uncertain questions out of twenty is `evaluation_drift`, an operational failure that stops escalation and acceptance rather than placing a systemic evaluator failure into the Human Review Queue as six separate question cases.

### Cost and topology comparison

At the researched standard `gpt-5.4-mini` list prices, one normal call reserves `$0.016875`; two reserve `$0.033750`. The optional high-reasoning call reserves `$0.034500`, so the quality cascade's maximum planned reservation is `$0.068250` across three attempts. These reservations assume no cache discount and include reasoning inside the OpenAI output ceiling.

One 20-question call is slightly cheaper but has a larger anchoring and malformed-response failure domain. Four five-question calls improve isolation only modestly while consuming two additional attempts. The existing four-specialist-plus-challenger topology can require roughly 100 quality calls for twenty questions and is rejected for Bootstrap Enrichment. Two batches of ten plus one uncertainty-only escalation preserve five of the pilot's twelve attempt slots for semantic repetition and post-quality work after four creative attempts.

The logic prototype is preserved on branch `codex/prototype-cascaded-quality-evaluation` at commit `6a110f0`. Its concrete cases demonstrate deterministic rejection, ordinary pass/reject evidence, uncertainty resolved both upward and downward, remaining uncertainty sent toward bounded review, the mandatory pending semantic gate, and a malformed batch that consumes cost without silently passing or retrying candidates. It uses simulated evidence and makes no paid API calls; measured model behavior remains a requirement of the later 20-candidate pilot.
