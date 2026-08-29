# Automated Evaluation Topology

## Purpose

The evaluation side of the Question Enrichment Pipeline decides whether a proposed Canonical Question is safe, understandable, properly classified, and globally distinct. It must preserve independent evidence and abstain when that evidence is incomplete or genuinely uncertain. It must not create the proposal it judges.

## Topology

```text
question proposal
      |
      v
deterministic preflight ---------------------------> reject critical failure
      |
      v
independent specialist judgments (in parallel)
      |
      +--> clarity and Bounded Openness
      +--> Level and safety
      +--> realism and question structure
      +--> ontology classification
      |
      v
high-recall bank-neighbor retrieval
      |
      v
facet-specific relation judgments
      |
      v
evidence consistency challenge
      |
      v
rule-based admission decision ----> accept | reject | Human Review Queue
```

## Stage Contracts

### 1. Deterministic Preflight

Check only facts that do not need creative judgment:

- all required proposal fields are present and structurally valid;
- exactly one approved Level is supplied;
- Question Provenance is complete;
- the source is permitted by the source policy;
- the proposal uses canonical English and contains only one question.

Unknown source permission, structurally invalid input, or another critical deterministic failure rejects the proposal before model evaluation. Preflight never decides that a question is creative or distinct.

### 2. Independent Specialist Judgments

Run the following evaluations independently and in parallel:

1. **Clarity and openness** checks understandable language, ordinary answerability, and Bounded Openness.
2. **Level and safety** checks that the proposed Level is correct, Shallow remains safe, and Deep invites characteristic but safe personal revelation.
3. **Realism and structure** checks that the situation feels plausible and that the text contains one clean question without unnecessary setup.
4. **Ontology classification** assigns Question Aspect, Semantic Scenario, Question Perspective, Answer Space, and Wording Pattern. Theme Membership is deliberately assigned later and is not an input to admission.

Every specialist returns a small structured record:

```text
check_name
rubric_version
verdict: pass | fail | uncertain
reason_code
concise_evidence
model_and_prompt_version
```

The first-pass records are immutable evaluation evidence. They are stored before any challenge stage sees them.

### 3. Bank-Neighbor Retrieval

Use lexical and semantic retrieval to obtain a high-recall shortlist from the entire active Question Bank. The retriever may use compact fingerprints and indexes, but its score is never an admission or duplicate verdict.

The proposal agents must not see the retrieved full questions. The relation judge receives only the candidate, the shortlisted neighbors, and the relation rubric it needs.

### 4. Facet-Specific Relation Judgments

Compare the candidate with every meaningful neighbor separately for:

- Wording Pattern;
- Semantic Scenario;
- Question Aspect;
- Question Perspective;
- Answer Space.

Do not collapse these relations into one similarity score. Sharing only an Aspect or Perspective is allowed. A strong semantic-repeat finding requires substantial coincidence of Semantic Scenario, Question Perspective, and Answer Space; wording similarity may strengthen the evidence but is not required.

Each comparison records the neighbor's stable identity, a result for every relation, a semantic-repeat result of `yes`, `no`, or `uncertain`, and concise evidence.

### 5. Evidence Consistency Challenge

After every independent record is preserved, a challenge stage may look for:

- contradictory specialist results;
- missing evidence;
- an unstable ontology assignment;
- a relation verdict unsupported by its facet results;
- a likely new failure pattern not covered by the current rubric or Reference Examples.

The challenger may flag a contradiction or request abstention. It cannot edit, average away, or silently replace a first-pass judgment. There is no free-form agent debate whose consensus becomes the answer.

### 6. Rule-Based Admission Decision

The decider is deterministic over structured evidence. It is independent from proposal production and does not use majority voting.

- **Reject** when a critical provenance, permission, safety, structure, quality, or global-distinctness gate clearly fails.
- **Accept** only when all critical evidence exists, every hard gate passes, the ontology assignment is stable, and no prohibited semantic repeat is found.
- **Human Review Queue** when a critical result is uncertain, specialists materially disagree, required evidence is missing, or the case appears outside the current rubric.

Missing evidence can never produce acceptance. Model or infrastructure failure therefore defaults to retrying the failed stage under the execution policy and then sending the intact proposal to the Human Review Queue if evidence still cannot be completed.

## Isolation Boundaries

Before producing a first-pass record, a specialist must not see:

- the proposal agent's identity or rationale;
- another evaluator's verdict or explanation;
- a discussion among evaluators;
- hidden human labels;
- unrelated full Question Bank text.

All evaluators receive the same candidate text and the versioned definition relevant to their check, but only the minimum additional context needed for their responsibility. Different model families may be used where they improve measured error diversity, but model count is not itself a quality guarantee.

## Disagreement and Confidence

- Preserve raw first-pass outputs even when later stages disagree.
- Never treat unanimous model votes as calibrated confidence.
- Calibrate the topology against the Reference Examples and occasional human spot checks.
- Add evaluators or debate stages only when those checks reveal a specific error that the added stage measurably reduces.
- Prefer an explicit `uncertain` result to invented precision.

## Evidence Retention

For every evaluated proposal, retain:

- proposal identity and Question Provenance;
- all independent structured judgments;
- the retrieved neighbor identities and index version;
- all facet-specific comparison results;
- the challenge result;
- the final rule and reason codes that fired;
- model, prompt, rubric, taxonomy, and bank snapshot versions;
- timestamps, retries, and execution failures.

Store concise evidence and reason codes, not private chain-of-thought.

## Prototype Findings

The logic prototype exercises four cases:

1. a clear, globally distinct Shallow question is accepted;
2. a polished paraphrase of an existing question is rejected as a semantic repeat;
3. an ambiguous Deep question preserves conflicting evidence and enters the Human Review Queue;
4. unknown source permission rejects before expensive model evaluation.

Prototype branch: `codex/prototype-automated-evaluation-topology`

Prototype commit: `e20f4dd`

Prototype file: `prototypes/automated_evaluation_topology.html`

## Consequences

- The system relies on evidence separation and calibrated abstention, not simulated committee confidence.
- The Question Bank Neighbor Index Module finds evidence; it is not an authority.
- Proposal creativity cannot be rewarded by relaxing hard admission gates.
- Human work is concentrated on actual ambiguity and new failure patterns rather than routine approval.
