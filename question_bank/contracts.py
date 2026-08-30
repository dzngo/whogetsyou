"""Versioned public records shared by Question Bank modules.

The records contain concise evidence and execution metadata only. Agents are never
asked to expose private chain-of-thought.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
DEFAULT_POLICY_VERSIONS = {
    "quality": "quality-v1",
    "admission": "admission-v1",
    "semantic_detection": "neighbor-relation-v1",
    "theme_classification": "theme-classifier-v1",
    "agent_configuration": "agent-config-v1",
    "safety": "safety-v1",
    "source_permission": "source-permission-v1",
    "coverage": "coverage-v1",
    "release": "release-v1",
    "revalidation": "whole-bank-revalidation-v1",
    "lifecycle": "lifecycle-v1",
    "scenario_family": "semantic-scenario-v1",
    "lexical_projection": "lexical-v1",
    "vector_projection": "hashed-ngram-vector-v1",
    "semantic_fingerprint_projection": "semantic-fingerprint-v1",
}


class QuestionLevel(str, Enum):
    SHALLOW = "shallow"
    DEEP = "deep"


class AdmissionDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"


class CoverageRegionKind(str, Enum):
    REQUIRED = "required"
    EXPLORATORY = "exploratory"
    INVALID = "invalid"


@dataclass
class EnrichmentBrief:
    brief_id: str
    idempotency_key: str
    level: QuestionLevel
    coverage_gap: Dict[str, Any]
    taxonomy_version_id: str
    snapshot_id: str
    concepts_per_scout: int = 5
    execution_run_id: str = ""
    version: int = SCHEMA_VERSION


@dataclass
class CreativeConcept:
    concept_id: str
    brief_id: str
    scout_role: str
    summary: str
    aspect_id: str
    perspective_id: str
    semantic_scenario: str
    answer_space: str
    taxonomy_status: str = "approved"
    source_invocation_id: str = ""
    version: int = SCHEMA_VERSION
    concise_evidence: str = ""


@dataclass
class QuestionProposal:
    proposal_id: str
    version: int
    idempotency_key: str
    text: str
    level: QuestionLevel
    aspect_id: str
    perspective_id: str
    semantic_scenario: str
    answer_space: str
    wording_pattern: str
    source_permission: str
    provenance: Dict[str, Any]


@dataclass
class ProposalBatch:
    brief_id: str
    concepts: List[CreativeConcept]
    proposals: List[QuestionProposal]
    diverted_taxonomy_concepts: List[CreativeConcept] = field(default_factory=list)
    failed_stage_items: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.failed_stage_items


@dataclass(frozen=True)
class EnrichmentRunResult:
    run_id: str
    brief_id: str
    proposal_ids: Tuple[str, ...]
    accepted_revision_ids: Tuple[str, ...]
    rejected_proposal_ids: Tuple[str, ...]
    review_case_ids: Tuple[str, ...]
    taxonomy_concept_ids: Tuple[str, ...]
    status: str
    concept_count: int = 0
    eligible_for_completion: bool = True


@dataclass
class AgentInvocation:
    invocation_id: str
    role: str
    provider: str
    model_preset: str
    provider_model: str
    reasoning_effort: Optional[str]
    prompt_version: str
    schema_version: int
    context_policy_version: str
    execution_version: str
    input_hash: str
    output_hash: str
    status: str
    concise_reason_codes: List[str] = field(default_factory=list)
    enrichment_run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    retry_count: int = 0
    error_details: List[str] = field(default_factory=list)
    provider_response_metadata: Dict[str, Any] = field(default_factory=dict)
    concise_evidence: str = ""


@dataclass
class SpecialistJudgment:
    judgment_id: str
    proposal_id: str
    role: str
    passed: bool
    uncertain: bool
    reason_codes: List[str]
    facet_values: Dict[str, str] = field(default_factory=dict)
    invocation_id: str = ""
    concise_evidence: str = ""


@dataclass
class NeighborEvidence:
    neighbor_revision_id: str
    question_text: str
    lexical_score: float
    ngram_cosine_score: float
    scenario: str
    perspective_id: str
    answer_space: str


@dataclass
class NeighborRelation:
    relation_id: str
    neighbor_revision_id: str
    semantic_repeat: bool
    uncertain: bool
    reason_codes: List[str]
    invocation_id: str
    scenario_relation: str = "unknown"
    perspective_relation: str = "unknown"
    answer_space_relation: str = "unknown"
    aspect_relation: str = "unknown"
    wording_pattern_relation: str = "unknown"
    concise_evidence: str = ""


@dataclass
class EvaluationEvidence:
    evidence_id: str
    proposal_id: str
    complete: bool
    hard_gate_failures: List[str]
    uncertainties: List[str]
    semantic_repeat: bool
    judge_invocation_ids: List[str]
    judgments: List[SpecialistJudgment] = field(default_factory=list)
    neighbor_relations: List[NeighborRelation] = field(default_factory=list)
    challenger_invocation_id: str = ""
    resolved_facets: Dict[str, str] = field(default_factory=dict)


@dataclass
class AdmissionOutcome:
    outcome_id: str
    proposal_id: str
    decision: AdmissionDecision
    authority: str
    evidence_id: str
    reason_codes: List[str]
    supersedes_outcome_id: Optional[str] = None


@dataclass
class EvaluationResult:
    evidence: EvaluationEvidence
    outcome: AdmissionOutcome


@dataclass
class ThemeClassification:
    classification_id: str
    proposal_id: str
    memberships: List[str]
    resolved: bool
    classifier_invocation_ids: List[str]
    uncertainties: List[str] = field(default_factory=list)
    concise_evidence: List[str] = field(default_factory=list)


@dataclass
class AcceptedQuestionPackage:
    idempotency_key: str
    proposal: QuestionProposal
    evidence: EvaluationEvidence
    outcome: AdmissionOutcome
    theme_classification: ThemeClassification
    taxonomy_version_id: str
    policy_versions: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_POLICY_VERSIONS)
    )
    named_theme_ids: List[str] = field(default_factory=list)
    approved_aspect_ids: List[str] = field(default_factory=list)
    approved_perspective_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuestionRevision:
    question_id: str
    revision_id: str
    revision_number: int
    text: str
    level: str
    theme_memberships: Tuple[str, ...]
    aspect_id: str
    perspective_id: str
    semantic_scenario: str
    answer_space: str
    wording_pattern: str
    lifecycle: str
    evidence_id: str
    provenance: Dict[str, Any]


@dataclass(frozen=True)
class LifecycleRecord:
    event_id: str
    question_id: str
    revision_id: str
    from_state: Optional[str]
    to_state: str
    reason: str


@dataclass(frozen=True)
class QuestionBankSnapshot:
    snapshot_id: str
    revision_ids: Tuple[str, ...]
    content_hash: str
    status: str = "candidate"


@dataclass
class ReviewRequest:
    request_id: str
    idempotency_key: str
    case_type: str
    proposal_id: str
    packet: Dict[str, Any]


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    request_id: str
    case_type: str
    status: str
    packet: Dict[str, Any]


@dataclass
class HumanResolution:
    idempotency_key: str
    action: str
    reason_codes: List[str]
    memberships: Optional[List[str]] = None
    edited_text: Optional[str] = None
    coverage_kind: Optional[str] = None
    taxonomy_change_package: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ResolutionResult:
    resolution_id: str
    case_id: str
    action: str
    status: str


@dataclass
class TaxonomyCandidate:
    candidate_id: str
    idempotency_key: str
    facet: str
    label: str
    definition: str
    supporting_concept_ids: List[str]
    aliases: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    positive_examples: List[str] = field(default_factory=list)
    counterexamples: List[str] = field(default_factory=list)
    closest_existing_taxa: List[str] = field(default_factory=list)
    explicit_differences: List[str] = field(default_factory=list)
    affected_taxon_ids: List[str] = field(default_factory=list)
    proposed_operation: str = "add"
    affected_revision_ids: List[str] = field(default_factory=list)
    reclassification_plan: Dict[str, str] = field(default_factory=dict)
    reference_regression_id: str = ""
    revalidation_evidence_ids: List[str] = field(default_factory=list)
    concise_evidence: str = ""
    replacement_taxa: List[Dict[str, Any]] = field(default_factory=list)
    independent_evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TaxonomyDecision:
    candidate_id: str
    decision: AdmissionDecision
    reason_codes: Tuple[str, ...]


@dataclass(frozen=True)
class TaxonomyVersion:
    version_id: str
    aspects: Tuple[str, ...]
    perspectives: Tuple[str, ...]
    content_hash: str
    released: bool


@dataclass
class CoverageRegion:
    region_id: str
    theme_id: str
    level: QuestionLevel
    aspect_id: str
    perspective_id: str
    kind: CoverageRegionKind
    minimum_distinct_scenarios: int = 3


@dataclass
class CoveragePlan:
    plan_id: str
    taxonomy_version_id: str
    regions: List[CoverageRegion]
    policy_version: str = "coverage-v1"


@dataclass(frozen=True)
class CoverageReport:
    report_id: str
    plan_id: str
    snapshot_id: str
    region_counts: Dict[str, int]
    scenario_counts: Dict[str, int]
    gaps: Tuple[str, ...]
    concentration_alerts: Tuple[str, ...]


@dataclass
class ReleaseIntent:
    idempotency_key: str
    revision_ids: List[str]
    taxonomy_version_id: str
    coverage_plan_id: str
    policy_versions: Dict[str, str]
    spot_check_passed: bool
    spot_check_id: Optional[str] = None
    retirement_revision_ids: List[str] = field(default_factory=list)
    completion_record_id: Optional[str] = None
    change_types: List[str] = field(default_factory=lambda: ["new_question"])


@dataclass(frozen=True)
class ReleaseReport:
    snapshot_id: str
    passed: bool
    gate_results: Dict[str, bool]
    reason_codes: Tuple[str, ...]


@dataclass(frozen=True)
class QuestionBankRelease:
    release_id: str
    snapshot_id: str
    content_hash: str
    status: str


@dataclass
class QuestionUsageEvent:
    event_id: str
    idempotency_key: str
    event_type: str
    session_pseudonym: str
    snapshot_id: str
    question_id: str
    revision_id: str
    round_id: str
    presentation_id: str
    selected_theme: str
    selected_level: str
    language: str
    origin: str


def record_dict(value: Any) -> Dict[str, Any]:
    """Convert dataclass records and enums into JSON-safe dictionaries."""
    def convert(item: Any) -> Any:
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, tuple):
            return [convert(value) for value in item]
        if isinstance(item, list):
            return [convert(value) for value in item]
        if isinstance(item, dict):
            return {key: convert(value) for key, value in item.items()}
        return item

    return convert(asdict(value))
