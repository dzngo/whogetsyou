# Define the Question Bank Record and Lifecycle

Type: grilling
Status: resolved
Blocked by: 01, 02, 05, 09

## Question

What is the identity and lifecycle of one Question Bank entry? Define canonical text identity, Theme and Level ownership, Angle/Perspective/scenario metadata, provenance, evaluation evidence, versioning, lifecycle states, immutability, correction and retirement behavior, and the interfaces that keep bank storage separate from proposal production and evaluation.

## Answer

A trusted entry exists only after final Accept authority and resolved Theme classification, and uses a stable Question ID plus immutable Question Revision IDs. Canonical text is content, not identity. Revisions preserve text, Level, zero-to-many resolved Theme Memberships, one approved Question Aspect and Perspective, Semantic Scenario, Answer Space, Wording Pattern, provenance, and evidence references; indexes and metrics are derived projections. The lifecycle is Staged, Active, or Retired, while Reject, unresolved Theme classification, and Human review remain outside trusted bank state. Text and metadata are never mutated in place. Proposal production, proposal evaluation, neighbor indexing, trusted Question Bank storage, and pipeline orchestration are separate deep modules with small interfaces; only the Question Bank module may create identity or change lifecycle.

## Comments

- Decision record: [`../question-bank-record-and-lifecycle.md`](../question-bank-record-and-lifecycle.md)
