# LLM Multi-Agent System Architecture

## Purpose

The Question Enrichment Pipeline is an offline LLM multi-agent system. Its primary job is to create a large, varied Question Bank automatically while using humans only for initial alignment, occasional spot checks, and genuinely uncertain cases.

An **LLM Agent** is one isolated, role-specific model invocation with a versioned prompt, limited context, structured input, and structured output. An agent is not a persistent persona and carries no hidden memory between runs. Agent roles may use different model families when measured evidence shows that doing so improves creativity or reduces correlated evaluation errors.

Deterministic Modules orchestrate the workflow, retrieve evidence, enforce schemas, apply decision rules, persist records, and publish releases. LLM Agents propose or judge semantic content; they never control trusted state directly.

## System Topology

```text
                           DETERMINISTIC CONTROL PLANE
          Taxonomy Registry + Coverage Planner + Pipeline Orchestrator
                                           |
                                           v
┌──────────────────────────────── LLM PROPOSAL GROUP ────────────────────────────────┐
│  Aspect Scout  ─┐                                                                  │
│  Scenario Scout ├─ parallel, isolated ─> Concept Relation Judge ─> Composer agents │
│  Perspective    ┤                                                                  │
│  Contrast Scout ┘                                                                  │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       | Question Proposals
                                       v
┌─────────────────────────────── LLM EVALUATION GROUP ───────────────────────────────┐
│  Clarity & Openness Judge ─┐                                                        │
│  Level & Safety Judge      ├─ parallel, isolated first-pass judgments               │
│  Realism & Structure Judge ┤                                                        │
│  Ontology Classifier      ─┘                                                        │
│                                       |                                             │
│  deterministic neighbor retrieval --> Relation Judges, parallel by neighbor         │
│                                       |                                             │
│                              Evidence Challenger                                    │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       |
                                       v
                        deterministic Admission Decider
                         /              |               \
                      Reject       Human review     automatic Accept
                                        |                |
                                  human Accept -----------+
                                                         |
                                                         v
┌──────────────────────────── LLM THEME CLASSIFICATION GROUP ────────────────────────┐
│         Theme Membership Classifier --> Theme Classification Challenger            │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       |
                              resolved zero-to-many Themes
                                       |
                                       v
                        deterministic Question Bank + Release

Repeated unclassified concepts
              |
              v
┌─────────────────────────────── LLM TAXONOMY GROUP ─────────────────────────────────┐
│ Taxonomy Candidate Author --> independent specialist judges --> adversarial         │
│ challenger --> shadow classifiers                                                   │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       |
                                       v
                          deterministic Taxonomy Decider
```

The control plane decides what work runs and whether sufficient evidence exists. It never substitutes deterministic rules for semantic judgment, and LLM outputs never directly write Question Bank or Taxonomy state.

## Agent Roster

### Proposal Group

| LLM Agent | Responsibility | Required input | Structured output | Must not see |
|---|---|---|---|---|
| Aspect Scout | Explore underrepresented subjects or life facets | Level, approved ontology, coverage gap, compact bank fingerprints | Creative Concepts | Other scouts' concepts, full bank text, Theme |
| Scenario Scout | Invent realistic concrete situations | Same creative brief | Creative Concepts | Other scouts' concepts, full bank text, Theme |
| Perspective Scout | Apply different lenses to ordinary material | Same creative brief | Creative Concepts | Other scouts' concepts, full bank text, Theme |
| Contrast Scout | Seek neglected trade-offs, boundaries, tolerances, and reversals | Same creative brief | Creative Concepts | Other scouts' concepts, full bank text, Theme |
| Concept Relation Judge | Compare concepts before wording and reject semantic convergence | Revealed concepts and diversity ontology | Separate Aspect, Scenario, Perspective, and Answer Space relations | Producer identity, future wording |
| Composer | Turn one surviving concept into one English question | One Creative Concept, Level, quality contract | One Question Proposal | Other concepts, full bank text, admission evidence |

The four scouts run concurrently and reveal outputs only after every first pass is stored. The Concept Relation Judge may process concept pairs concurrently. Each surviving concept receives a separate Composer invocation so one composition context cannot make the entire batch stylistically uniform.

### Evaluation Group

| LLM Agent | Responsibility | Required input | Structured output | Must not see before first pass |
|---|---|---|---|---|
| Clarity & Openness Judge | Check understandable text, ordinary answerability, and Bounded Openness | Question text, relevant rubric | Pass/fail/uncertain, reason code, concise evidence | Producer identity, other verdicts |
| Level & Safety Judge | Check intended Level, safety, and Deep personal revelation | Question text, Level rubric | Pass/fail/uncertain, reason code, concise evidence | Producer identity, other verdicts |
| Realism & Structure Judge | Check plausibility and single-question structure | Question text, structure rubric | Pass/fail/uncertain, reason code, concise evidence | Producer identity, other verdicts |
| Ontology Classifier | Assign Aspect, Scenario, Perspective, Answer Space, and Wording Pattern | Question text, approved Taxonomy Version | Facet assignments with uncertainty | Producer identity, coverage pressure, Theme |
| Relation Judge | Compare a proposal with one retrieved bank neighbor across separate facets | Candidate, one neighbor, relation rubric | Per-facet relations and repeat yes/no/uncertain | Retrieval score as a verdict, peer comparisons |
| Evidence Challenger | Find contradictions, missing evidence, and unfamiliar failure patterns | Preserved first-pass evidence | Challenge result and reason codes | Private chain-of-thought |

The first four judges run concurrently in isolated contexts. Question Bank neighbor retrieval is deterministic and begins after ontology classification. Relation Judge calls run concurrently across shortlisted neighbors. The Evidence Challenger runs only after every first-pass judgment has been stored and cannot overwrite it.

The deterministic Admission Decider applies the approved rules to these structured outputs. There is no LLM majority vote and no discussion round whose consensus becomes bank authority.

### Theme Classification Group

| LLM Agent | Responsibility | Required input | Structured output |
|---|---|---|---|
| Theme Membership Classifier | Assign zero-to-many equal Named Theme memberships after final Accept | Accepted question, Level, Named Theme definitions | Proposed membership set, including confidently empty, with concise evidence |
| Theme Classification Challenger | Look for unsupported memberships and important omissions | Question, proposed memberships, Theme definitions | Confirmed set or uncertainty reason |

This group cannot change the Admission Outcome. Agreement produces the resolved Theme classification required for bank identity. Unresolved disagreement enters the Human Review Queue.

### Taxonomy Group

| LLM Agent | Responsibility | Required input | Structured output |
|---|---|---|---|
| Taxonomy Candidate Author | Explain a repeated classification gap | Independently produced unclassified concepts, current taxonomy | Candidate name, definition, examples, exclusions, closest taxa |
| Kind Judge | Distinguish Aspect from Perspective and other facets | Candidate and ontology definitions | Pass/fail/uncertain |
| Distinctness Judge | Detect synonyms, trivial narrowing, or compound labels | Candidate and nearest existing taxa | Relation judgments |
| Reusability Judge | Test whether the term applies beyond one wording or scenario | Candidate and supporting concepts | Pass/fail/uncertain |
| Classification Stability Judge | Apply the definition consistently to shuffled positives and negatives | Candidate definition and shadow set | Classifications and uncertainty |
| Variety Value Judge | Test whether the term reveals a meaningful coverage region rather than adding label count | Candidate, support, Coverage Plan | Pass/fail/uncertain |
| Safety & Neutrality Judge | Detect harmful assumptions or dependence on one Named Theme | Candidate definition, examples, exclusions | Pass/fail/uncertain |
| Taxonomy Challenger | Try to absorb the candidate into existing terms and find counterexamples | Candidate, current taxonomy, shadow set | Challenges and reason codes |
| Shadow Classifiers | Test the candidate without relying on its label | Mixed shuffled examples | Independent classifications |

Specialist taxonomy judges run concurrently. The challenger runs after their first-pass evidence is stored. At least two isolated shadow-classifier calls are used in the starting configuration; model-family diversity is added only when Reference Example or audit results show that it reduces correlated errors.

## LLM Agent Contract

Every invocation receives an **Agent Configuration**:

```text
agent_role
agent_contract_version
model_provider
requested_model
reported_model_identity
reasoning_effort
generation_parameters
system_prompt_hash
task_prompt_hash
input_schema_version
output_schema_version
context_policy_version
rubric_or_taxonomy_version
timeout
retry_limit
```

Every output envelope contains:

```text
invocation_id
enrichment_run_id
agent_role
configuration_id
input_hash
structured_result
verdict_or_status
reason_codes[]
concise_evidence
uncertainty
started_at
completed_at
provider_response_metadata
```

Prompts require schema-conformant outputs and an explicit uncertainty path. Private chain-of-thought is neither requested nor stored. Concise evidence must identify the relevant rubric fact without exposing hidden reasoning.

## Context Isolation Policy

Context isolation is a reliability feature, not merely a prompting preference.

| Context item | Proposal scouts | Composer | First-pass evaluators | Relation Judge | Challenger | Theme group | Taxonomy agents |
|---|---:|---:|---:|---:|---:|---:|---:|
| Candidate Question | Not yet created | No; concept only | Yes | Yes | Yes | Yes, after Accept | Supporting examples only |
| Selected Level | Yes | Yes | Yes | Yes | Yes | Yes | When relevant |
| Selected Theme | No | No | No | No | No | Named Theme definitions only | Definitions only when testing Theme confusion |
| Coverage gap | Yes | No | No | No | No | No | Repeated gap only |
| Full bank questions | No | No | No | Retrieved neighbor only | Evidence references only | No | Mixed shadow examples only |
| Other same-stage outputs before first pass | No | Not applicable | No | No | Yes, after preservation | Challenger sees classifier output | No |
| Producer identity or rationale | Own role only | Concept only | No | No | No | No | Candidate provenance without agent prestige |
| Human expected outcome | No | No | No | No | No | No | No |

The orchestrator constructs a new context packet for every invocation. It never forwards conversation history by default. Only declared structured fields cross agent seams.

## Model Assignment Policy

Agent role and LLM model are separate decisions. One model may initially serve several roles, but every role has its own prompt and isolated invocation.

Choose models by measured role performance:

1. Test candidate models on the roughly thirty Reference Examples and purpose-built role cases.
2. Measure creativity, quality-gate accuracy, semantic-repeat errors, abstention behavior, structured-output reliability, cost, and latency separately.
3. Prefer the simplest and least expensive model configuration that meets the role's quality requirement.
4. Use a stronger creative model for scout or Composer roles when it produces meaningfully more distinct accepted questions.
5. Use a different model family for critical judges only when audits show that it reduces correlated errors; different model names alone do not prove independence.
6. Pin every released pipeline to an Agent Configuration set. A material model or prompt change triggers the defined revalidation and spot-check rules.

The architecture therefore fixes roles, information boundaries, and decision authority while allowing model choices to improve over time.

## Parallelism and Ordering

Run concurrently when contexts are independent:

- four proposal scouts;
- first-pass evaluation specialists;
- relation comparisons across retrieved neighbors;
- taxonomy specialist judges;
- shadow classifiers;
- Composer calls for different surviving concepts.

Run sequentially when later work requires preserved evidence:

1. proposal scouts before concept comparison;
2. concept comparison before composition;
3. composition before evaluation;
4. first-pass evaluation before neighbor relation adjudication and challenge;
5. all evaluation evidence before deterministic admission;
6. final Accept before Theme classification;
7. resolved Theme classification before bank identity;
8. taxonomy support before candidate authorship, challenge, and release;
9. bank staging before snapshot verification and release.

Concurrency is limited by a versioned per-run cost and rate-limit budget. Worker count changes throughput, not decision semantics.

## Reliability and Failure Behavior

- Validate every LLM output against its schema before using it.
- Retry one failed invocation with the same input and Agent Configuration.
- Evaluation evidence still missing after retry makes Accept impossible and enters human review.
- A failed proposal scout is requeued; surviving concepts may proceed, but the incomplete batch cannot count toward coverage-completion evidence.
- A failed Composer affects only its concept and may be requeued without repeating other compositions.
- Failed taxonomy judgments prevent taxonomy acceptance or release.
- Persist first-pass outputs before running any Challenger.
- Use stable idempotency keys so retries cannot create duplicate proposals, evidence, questions, or decisions.
- Evaluate against a fixed Question Bank Snapshot and Taxonomy Version throughout one run.
- Stop or throttle new work when cost, failure-rate, review-queue, or provider health limits are exceeded; already trusted bank content remains unaffected.

## Creativity Safeguards

- Give scouts different semantic missions rather than the same prompt with different role names.
- Hide other scouts' ideas until independent outputs are committed.
- Work with Creative Concepts before phrasing so variety is semantic rather than cosmetic.
- Hide full bank wording from proposal agents to reduce imitation and prompt size.
- Use compact coverage and novelty fingerprints to direct exploration without anchoring wording.
- Compose each concept separately.
- Reject or merge overlapping concepts before spending evaluation work.
- If a batch converges, generate a new gap brief instead of requesting paraphrases.

## Minimal Human Loop

LLM Agents handle normal generation, classification, evaluation, challenge, taxonomy proposals, Theme assignment, and revalidation automatically. Deterministic Modules handle final authority and trusted state.

Human involvement is limited to:

- confirming roughly thirty initial Reference Examples;
- reviewing cases where agents explicitly abstain or materially disagree;
- resolving uncertain post-accept Theme classifications or taxonomy changes;
- inspecting ten accepted questions in the first batch and after material pipeline changes;
- diagnosing a repeated defect when a spot check fails.

No person approves every question, monitors every agent run, or selects among routine agent outputs.

## Starting Agent Configuration

The first implementation should use this logical topology before experimenting with more agents:

- 4 parallel proposal scouts;
- 1 Concept Relation Judge applied across concept pairs;
- 1 Composer invocation per surviving concept;
- 4 parallel first-pass evaluation specialists;
- 1 Relation Judge contract applied independently per retrieved neighbor;
- 1 Evidence Challenger;
- 1 deterministic Admission Decider;
- 1 Theme Membership Classifier plus 1 Theme Classification Challenger;
- 1 Taxonomy Candidate Author, 6 taxonomy specialist contracts, 1 Taxonomy Challenger, and at least 2 shadow-classifier invocations when the taxonomy path runs.

This is a logical agent count, not a requirement for separate deployed processes or separate model providers. Add, remove, or diversify agents only when Reference Examples and spot checks identify a specific error and demonstrate that the topology change improves it.

## Consequences

- The design is explicitly an LLM multi-agent system, while trusted decisions remain deterministic and auditable.
- Creative agents and evaluation agents have different authority and cannot reinforce their own output.
- Parallel isolated first passes create useful diversity without letting early consensus hide disagreement.
- Model choices can evolve without changing the domain workflow or bank identity.
- The normal path remains automatic, with human attention reserved for true uncertainty.
