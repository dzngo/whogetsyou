# Prototype the Diversity Ontology with Real Questions

Type: prototype
Status: resolved

## Question

Using representative strong, weak, and repetitive questions from the current system, what minimal content model lets humans and agents consistently distinguish Question Angle, Question Perspective, semantic scenario, answer space, and wording structure? Produce and label a rough example corpus that makes ambiguous boundaries concrete enough for the user to approve or revise.

## Comments

The interactive logic prototype is captured on branch `codex/prototype-question-bank-diversity-ontology` at commit `4a2e01f` in `prototypes/question_bank_diversity_ontology.html`.

It compares five difficult pairs using separate Theme Membership, Question Aspect, semantic scenario, Question Perspective, answer-space, and wording-pattern relations. It also pressure-tests a global Question Aspect against the existing model where each Question Angle belongs to one Theme.

## Answer

The approved model is recorded in [`diversity-ontology.md`](../diversity-ontology.md). The user validated the prototype's complete facet set and its treatment of partial overlap.

Question Bank entries use exactly one Level, zero or more equal Theme Memberships, and one global Question Aspect, Semantic Scenario, Question Perspective, Answer Space, and Wording Pattern. Question Aspect replaces Theme-owned Question Angle for bank classification; the existing Question Angle Catalog remains a legacy generation aid. Sharing only an Aspect or Perspective is acceptable, while substantial coincidence of Scenario, Perspective, and Answer Space makes a pair a strong semantic-repeat candidate. No single aggregate similarity score is authoritative.
