# Design the Automated Evaluation Topology

Type: prototype
Status: resolved
Blocked by: 01, 02, 03, 04, 06

## Question

What concrete arrangement of independent critics, specialist evaluators, adversarial checks, semantic-comparison stages, aggregators, and abstaining decision makers can judge creativity and quality without letting one model's assumptions or shared context dominate? Prototype the evidence flow, isolation boundaries, structured outputs, disagreement handling, and failure behavior of the evaluation side of the Question Enrichment Pipeline.

## Answer

Use a deterministic preflight followed by isolated specialist judgments for clarity/openness, Level/safety, realism/structure, and ontology classification. Preserve those structured first-pass records before a high-recall retriever finds bank neighbors and a separate judge compares Wording Pattern, Semantic Scenario, Question Aspect, Question Perspective, and Answer Space independently. A challenge stage may flag contradictions but cannot overwrite evidence. A rule-based decider accepts only complete passing evidence with no semantic repeat, rejects clear critical failures, and sends uncertainty, disagreement, missing evidence, and novel failure patterns to the Human Review Queue. No proposal agent judges its own output, and model consensus is never treated as confidence.

The runnable logic prototype covers automatic acceptance, semantic-repeat rejection, uncertain human review, and deterministic source-permission rejection.

## Comments

- Decision record: [`../automated-evaluation-topology.md`](../automated-evaluation-topology.md)
- Prototype branch: `codex/prototype-automated-evaluation-topology`
- Prototype commit: `e20f4dd`
- Prototype path: `prototypes/automated_evaluation_topology.html`
