"""Isolated, structured LLM agent groups for autonomous enrichment."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Type,
)

from pydantic import BaseModel, Field

from models import resolve_llm_model
from question_bank.contracts import (
    AgentInvocation,
    CoverageRegion,
    CoverageRegionKind,
    CreativeConcept,
    EnrichmentBrief,
    EvaluationEvidence,
    EvaluationResult,
    NeighborRelation,
    ProposalBatch,
    QuestionLevel,
    QuestionProposal,
    ReviewRequest,
    SpecialistJudgment,
    TaxonomyCandidate,
    TaxonomyDecision,
    ThemeClassification,
    record_dict,
)
from question_bank.core import AdmissionDecider, QuestionBank, _stable_hash
from question_bank.modules import (
    CoveragePlanner,
    HumanReview,
    QuestionBankNeighborIndex,
    ReferenceExampleRegistry,
    TaxonomyRegistry,
)
from services.llm_loader import get_llm


class StructuredLLM(Protocol):
    model_name: str

    def parse_structured(self, messages: Sequence[Dict[str, str]], response_model: Any) -> Any: ...


class ConceptOutput(BaseModel):
    summary: str
    aspect_id: str
    perspective_id: str
    semantic_scenario: str
    answer_space: str
    taxonomy_status: str = "approved"
    concise_evidence: str = Field(min_length=1, max_length=800)


class ConceptBatchOutput(BaseModel):
    concepts: List[ConceptOutput]
    concise_evidence: str = Field(min_length=1, max_length=800)


class ConceptDedupOutput(BaseModel):
    keep_concept_ids: List[str] = Field(default_factory=list)
    concise_evidence: str = Field(min_length=1, max_length=800)


class ProposalOutput(BaseModel):
    question: str
    wording_pattern: str
    concise_evidence: str = Field(min_length=1, max_length=800)


class JudgmentOutput(BaseModel):
    passed: bool
    uncertain: bool
    reason_codes: List[str]
    facet_values: Dict[str, str] = Field(default_factory=dict)
    concise_evidence: str = Field(min_length=1, max_length=800)


class RelationOutput(BaseModel):
    semantic_repeat: bool
    uncertain: bool
    reason_codes: List[str]
    scenario_relation: str
    perspective_relation: str
    answer_space_relation: str
    aspect_relation: str
    wording_pattern_relation: str
    concise_evidence: str = Field(min_length=1, max_length=800)


class ChallengeOutput(BaseModel):
    complete: bool
    uncertainty_reason_codes: List[str]
    concise_evidence: str = Field(min_length=1, max_length=800)


class ThemeOutput(BaseModel):
    memberships: List[str]
    uncertain: bool
    reason_codes: List[str]
    concise_evidence: str = Field(min_length=1, max_length=800)


class CoverageRegionOutput(BaseModel):
    kind: CoverageRegionKind
    uncertain: bool
    reason_codes: List[str]
    concise_evidence: str = Field(min_length=1, max_length=800)


class ReplacementTaxonOutput(BaseModel):
    label: str
    definition: str
    aliases: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)


class TaxonomyCandidateOutput(BaseModel):
    facet: str
    label: str
    definition: str
    aliases: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    positive_examples: List[str] = Field(default_factory=list)
    counterexamples: List[str] = Field(default_factory=list)
    closest_existing_taxa: List[str] = Field(default_factory=list)
    explicit_differences: List[str] = Field(default_factory=list)
    affected_taxon_ids: List[str] = Field(default_factory=list)
    proposed_operation: str = "add"
    replacement_taxa: List[ReplacementTaxonOutput] = Field(default_factory=list)
    concise_evidence: str = Field(min_length=1, max_length=800)


class ModelRouting:
    """Versioned role-to-model policy; no role selects its own model."""

    SCOUT_ROLES = ("aspect_scout", "scenario_scout", "perspective_scout", "contrast_scout")
    EVALUATION_ROLES = (
        "clarity_openness_judge",
        "level_safety_judge",
        "realism_structure_judge",
        "ontology_judge",
    )
    CREATIVE_PRESET = "gemini-3.5-flash-high"
    JUDGE_PRESET = "gpt-5.4-mini-high"

    def preset_for(self, role: str) -> str:
        creative = {*self.SCOUT_ROLES, "composer", "taxonomy_candidate_author"}
        return self.CREATIVE_PRESET if role in creative else self.JUDGE_PRESET


class AgentRunner:
    """Executes one isolated agent call, retries once, and records its envelope."""

    def __init__(
        self,
        database_path: Path | str,
        llm_factory: Callable[[str], StructuredLLM] = get_llm,
        routing: Optional[ModelRouting] = None,
        execution_version: str = "agent-runner-v1",
    ) -> None:
        self._db = sqlite3.connect(str(database_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS agent_invocations (
                invocation_id TEXT PRIMARY KEY, role TEXT NOT NULL, provider TEXT NOT NULL,
                model_preset TEXT NOT NULL, provider_model TEXT NOT NULL, reasoning_effort TEXT,
                prompt_version TEXT NOT NULL, schema_version INTEGER NOT NULL,
                context_policy_version TEXT NOT NULL, execution_version TEXT NOT NULL,
                input_hash TEXT NOT NULL, output_hash TEXT NOT NULL, status TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL, configuration_json TEXT NOT NULL,
                input_json TEXT NOT NULL, structured_output_json TEXT NOT NULL,
                enrichment_run_id TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '', retry_count INTEGER NOT NULL DEFAULT 0,
                error_json TEXT NOT NULL DEFAULT '[]', response_metadata_json TEXT NOT NULL DEFAULT '{}',
                concise_evidence TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        invocation_columns = {
            row[1] for row in self._db.execute("PRAGMA table_info(agent_invocations)")
        }
        for name, definition in (
            ("enrichment_run_id", "TEXT NOT NULL DEFAULT ''"),
            ("started_at", "TEXT NOT NULL DEFAULT ''"),
            ("completed_at", "TEXT NOT NULL DEFAULT ''"),
            ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ("error_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("response_metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("concise_evidence", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in invocation_columns:
                self._db.execute(f"ALTER TABLE agent_invocations ADD COLUMN {name} {definition}")
        self._db.commit()
        self._lock = threading.Lock()
        self._llm_factory = llm_factory
        self.routing = routing or ModelRouting()
        self.execution_version = execution_version

    def close(self) -> None:
        self._db.close()

    def has_successful_invocations(self, invocation_ids: Sequence[str]) -> bool:
        identifiers = sorted(set(invocation_ids))
        if not identifiers:
            return True
        placeholders = ",".join("?" for _ in identifiers)
        rows = self._db.execute(
            f"""SELECT invocation_id FROM agent_invocations
                WHERE invocation_id IN ({placeholders})
                  AND status IN ('succeeded', 'cache_reused')""",
            identifiers,
        ).fetchall()
        return len(rows) == len(identifiers)

    def invoke(
        self,
        role: str,
        instructions: str,
        payload: Dict[str, Any],
        response_model: Type[BaseModel],
        prompt_version: str = "v1",
        context_policy_version: str = "isolated-v1",
    ) -> Tuple[BaseModel, AgentInvocation]:
        preset = self.routing.preset_for(role)
        config = resolve_llm_model(preset)
        provider_model = config.provider_model
        reasoning = config.reasoning_effort
        provider = config.provider
        model_payload = dict(payload)
        model_payload.pop("enrichment_run_id", None)
        if isinstance(model_payload.get("proposal"), dict):
            model_payload["proposal"] = dict(model_payload["proposal"])
            model_payload["proposal"].pop("enrichment_run_id", None)
        messages = [
            {
                "role": "system",
                "content": (
                    f"ROLE: {role}\n{instructions}\n"
                    "Return only the requested structured result. Give concise reason codes, never private chain-of-thought."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(model_payload, sort_keys=True, ensure_ascii=False),
            },
        ]
        nested_proposal = payload.get("proposal", {})
        run_id = str(
            payload.get("enrichment_run_id")
            or (
                nested_proposal.get("enrichment_run_id", "")
                if isinstance(nested_proposal, dict)
                else ""
            )
        )
        schema_hash = _stable_hash(response_model.model_json_schema())
        input_hash = _stable_hash(
            {
                "messages": messages,
                "model_preset": preset,
                "provider_model": provider_model,
                "reasoning_effort": reasoning,
                "execution_version": self.execution_version,
                "schema_hash": schema_hash,
            }
        )
        cached = self._cached_success(
            role,
            input_hash,
            prompt_version,
            context_policy_version,
            response_model,
            provider,
            preset,
            provider_model,
            reasoning,
            run_id,
            messages,
            schema_hash,
        )
        if cached is not None:
            return cached
        failure: Optional[Exception] = None
        output: Optional[BaseModel] = None
        errors = []
        retry_count = 0
        started_at = datetime.now(timezone.utc).isoformat()
        llm: Optional[StructuredLLM] = None
        for attempt in range(2):
            try:
                llm = self._llm_factory(preset)
                output = llm.parse_structured(messages, response_model)
                break
            except Exception as error:  # external boundary; one policy-approved execution retry
                failure = error
                errors.append(type(error).__name__)
                retry_count = min(attempt + 1, 1)
        completed_at = datetime.now(timezone.utc).isoformat()
        if output is None:
            self._store_failed(
                role,
                provider,
                preset,
                provider_model,
                reasoning,
                prompt_version,
                context_policy_version,
                input_hash,
                messages,
                run_id,
                started_at,
                completed_at,
                retry_count,
                errors,
            )
            raise RuntimeError(f"agent stage {role} failed after one retry") from failure
        output_payload = output.model_dump(mode="json")
        response_metadata = dict(getattr(llm, "last_response_metadata", {}))
        reported_model = str(response_metadata.get("reported_model", provider_model))
        invocation = AgentInvocation(
            invocation_id=f"inv-{uuid.uuid4().hex}",
            role=role,
            provider=provider,
            model_preset=preset,
            provider_model=reported_model,
            reasoning_effort=reasoning,
            prompt_version=prompt_version,
            schema_version=1,
            context_policy_version=context_policy_version,
            execution_version=self.execution_version,
            input_hash=input_hash,
            output_hash=_stable_hash(output_payload),
            status="succeeded",
            concise_reason_codes=list(output_payload.get("reason_codes", [])),
            enrichment_run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            retry_count=retry_count,
            error_details=errors,
            provider_response_metadata=response_metadata,
            concise_evidence=str(output_payload.get("concise_evidence", "")),
        )
        configuration = {
            "agent_role": role,
            "agent_contract_version": prompt_version,
            "model_provider": provider,
            "requested_model": preset,
            "reported_model_identity": reported_model,
            "reasoning_effort": reasoning,
            "generation_parameters": {},
            "input_schema_version": 1,
            "output_schema_version": 1,
            "output_schema_hash": schema_hash,
            "context_policy_version": context_policy_version,
            "timeout_seconds": getattr(llm, "timeout_seconds", None),
            "retry_limit": 1,
        }
        self._persist(invocation, messages, output_payload, configuration)
        return output, invocation

    def _cached_success(
        self,
        role: str,
        input_hash: str,
        prompt_version: str,
        context_policy_version: str,
        response_model: Type[BaseModel],
        provider: str,
        preset: str,
        provider_model: str,
        reasoning: Optional[str],
        run_id: str,
        messages: Sequence[Dict[str, str]],
        schema_hash: str,
    ) -> Optional[Tuple[BaseModel, AgentInvocation]]:
        with self._lock:
            row = self._db.execute(
                """SELECT * FROM agent_invocations
                   WHERE role = ? AND input_hash = ? AND prompt_version = ?
                     AND context_policy_version = ? AND model_preset = ?
                     AND provider_model = ? AND execution_version = ?
                     AND status = 'succeeded'
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (
                    role,
                    input_hash,
                    prompt_version,
                    context_policy_version,
                    preset,
                    provider_model,
                    self.execution_version,
                ),
            ).fetchone()
        if not row:
            return None
        output = response_model.model_validate(json.loads(row["structured_output_json"]))
        now = datetime.now(timezone.utc).isoformat()
        invocation = AgentInvocation(
            invocation_id=f"inv-{uuid.uuid4().hex}",
            role=role,
            provider=provider,
            model_preset=preset,
            provider_model=provider_model,
            reasoning_effort=reasoning,
            prompt_version=prompt_version,
            schema_version=1,
            context_policy_version=context_policy_version,
            execution_version=self.execution_version,
            input_hash=input_hash,
            output_hash=row["output_hash"],
            status="cache_reused",
            concise_reason_codes=json.loads(row["reason_codes_json"]),
            enrichment_run_id=run_id,
            started_at=now,
            completed_at=now,
            retry_count=0,
            error_details=[],
            provider_response_metadata={"cache_source_invocation_id": row["invocation_id"]},
            concise_evidence=row["concise_evidence"],
        )
        configuration = {
            "agent_role": role,
            "agent_contract_version": prompt_version,
            "model_provider": provider,
            "requested_model": preset,
            "reported_model_identity": provider_model,
            "reasoning_effort": reasoning,
            "generation_parameters": {},
            "input_schema_version": 1,
            "output_schema_version": 1,
            "output_schema_hash": schema_hash,
            "context_policy_version": context_policy_version,
            "timeout_seconds": 60,
            "retry_limit": 1,
            "cache_source_invocation_id": row["invocation_id"],
        }
        self._persist(
            invocation,
            messages,
            output.model_dump(mode="json"),
            configuration,
        )
        return output, invocation

    def _store_failed(
        self,
        role,
        provider,
        preset,
        provider_model,
        reasoning,
        prompt_version,
        context_policy_version,
        input_hash,
        input_messages,
        enrichment_run_id,
        started_at,
        completed_at,
        retry_count,
        errors,
    ):
        invocation = AgentInvocation(
            f"inv-{uuid.uuid4().hex}", role, provider, preset, provider_model, reasoning, prompt_version, 1,
            context_policy_version, self.execution_version, input_hash, "", "failed", ["execution_failed_after_retry"],
            enrichment_run_id, started_at, completed_at, retry_count, errors, {},
        )
        configuration = {
            "agent_role": role,
            "agent_contract_version": prompt_version,
            "model_provider": provider,
            "requested_model": preset,
            "reported_model_identity": provider_model,
            "reasoning_effort": reasoning,
            "generation_parameters": {},
            "input_schema_version": 1,
            "output_schema_version": 1,
            "context_policy_version": context_policy_version,
            "timeout_seconds": 60,
            "retry_limit": 1,
        }
        self._persist(invocation, input_messages, {}, configuration)

    def _persist(
        self,
        invocation: AgentInvocation,
        input_messages: Sequence[Dict[str, str]],
        structured_output: Dict[str, Any],
        configuration: Dict[str, Any],
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                """INSERT INTO agent_invocations(
                       invocation_id, role, provider, model_preset, provider_model,
                       reasoning_effort, prompt_version, schema_version,
                       context_policy_version, execution_version, input_hash, output_hash,
                       status, reason_codes_json, configuration_json, input_json,
                       structured_output_json, enrichment_run_id, started_at, completed_at,
                       retry_count, error_json, response_metadata_json, concise_evidence
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    invocation.invocation_id,
                    invocation.role,
                    invocation.provider,
                    invocation.model_preset,
                    invocation.provider_model,
                    invocation.reasoning_effort,
                    invocation.prompt_version,
                    invocation.schema_version,
                    invocation.context_policy_version,
                    invocation.execution_version,
                    invocation.input_hash,
                    invocation.output_hash,
                    invocation.status,
                    json.dumps(invocation.concise_reason_codes),
                    json.dumps(configuration, sort_keys=True),
                    json.dumps(list(input_messages), sort_keys=True, ensure_ascii=False),
                    json.dumps(structured_output, sort_keys=True, ensure_ascii=False),
                    invocation.enrichment_run_id,
                    invocation.started_at,
                    invocation.completed_at,
                    invocation.retry_count,
                    json.dumps(invocation.error_details),
                    json.dumps(invocation.provider_response_metadata, sort_keys=True),
                    invocation.concise_evidence,
                ),
            )


class ProposalProduction:
    """Four isolated scouts, concept relation judge, then one composer per concept."""

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def propose(self, enrichment_brief: EnrichmentBrief) -> ProposalBatch:
        # The selected Theme is intentionally removed from every creative context.
        creative_gap = {
            key: value
            for key, value in enrichment_brief.coverage_gap.items()
            if key.lower() not in {"theme", "theme_id", "named_theme", "theme_membership"}
        }
        payload = {
            "enrichment_run_id": enrichment_brief.execution_run_id,
            "level": enrichment_brief.level.value,
            "coverage_gap": creative_gap,
            "concept_count": enrichment_brief.concepts_per_scout,
            "quality_goal": "maximize semantic variety; deep prompts invite safe characteristic self-revelation",
        }

        missions = {
            "aspect_scout": "Explore different subjects or life facets without changing the requested level.",
            "scenario_scout": "Explore concrete situations and moments that create different answer spaces.",
            "perspective_scout": "Explore different lenses, stances, and frames on the same broad territory.",
            "contrast_scout": "Seek underrepresented contrasts and avoid the most obvious concept family.",
        }

        def scout(role: str):
            try:
                return role, self._runner.invoke(
                    role,
                    f"{missions[role]} Develop distinct concepts; do not write final questions.",
                    payload,
                    ConceptBatchOutput,
                    "proposal-scout-v1",
                ), None
            except Exception as error:
                return role, None, type(error).__name__

        concepts: List[CreativeConcept] = []
        failed_stage_items: List[str] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for role, invoked, error_type in pool.map(scout, ModelRouting.SCOUT_ROLES):
                if invoked is None:
                    failed_stage_items.append(f"scout:{role}:{error_type}")
                    continue
                result, scout_invocation = invoked
                for index, item in enumerate(result.concepts):
                    concept_id = f"concept-{_stable_hash([enrichment_brief.brief_id, role, index, item.model_dump()])[:20]}"
                    concepts.append(
                        CreativeConcept(
                            concept_id,
                            enrichment_brief.brief_id,
                            role,
                            item.summary,
                            item.aspect_id,
                            item.perspective_id,
                            item.semantic_scenario,
                            item.answer_space,
                            item.taxonomy_status,
                            scout_invocation.invocation_id,
                            concise_evidence=item.concise_evidence,
                        )
                    )
        try:
            dedup, dedup_invocation = self._runner.invoke(
                "concept_relation_judge",
                "Identify concepts that substantially repeat scenario, perspective, and answer space. Keep distinct concepts.",
                {
                    "enrichment_run_id": enrichment_brief.execution_run_id,
                    "concepts": [self._concept_context(concept) for concept in concepts],
                },
                ConceptDedupOutput,
                "concept-relation-v1",
            )
        except Exception as error:
            failed_stage_items.append(f"concept_relation_judge:{type(error).__name__}")
            return ProposalBatch(
                enrichment_brief.brief_id,
                [concept for concept in concepts if concept.taxonomy_status == "approved"],
                [],
                [],
                failed_stage_items,
            )
        keep = set(dedup.keep_concept_ids)
        approved = [
            concept
            for concept in concepts
            if concept.taxonomy_status == "approved" and concept.concept_id in keep
        ]
        diverted = [
            concept
            for concept in concepts
            if concept.taxonomy_status != "approved" and concept.concept_id in keep
        ]

        def compose(concept: CreativeConcept):
            try:
                output, invocation = self._runner.invoke(
                    "composer",
                    "Write exactly one understandable, bounded-open question. Output only the question and its wording pattern.",
                    {
                        "enrichment_run_id": enrichment_brief.execution_run_id,
                        "level": enrichment_brief.level.value,
                        "concept": self._concept_context(concept),
                    },
                    ProposalOutput,
                    "composer-v1",
                )
            except Exception as error:
                return concept.concept_id, None, type(error).__name__
            proposal_id = f"proposal-{_stable_hash([concept.concept_id, output.question])[:20]}"
            return concept.concept_id, QuestionProposal(
                proposal_id,
                1,
                f"proposal-key-{proposal_id}",
                output.question.strip(),
                enrichment_brief.level,
                concept.aspect_id,
                concept.perspective_id,
                concept.semantic_scenario,
                concept.answer_space,
                output.wording_pattern,
                "de_novo",
                {
                    "brief_id": enrichment_brief.brief_id,
                    "enrichment_run_id": enrichment_brief.execution_run_id,
                    "concept_id": concept.concept_id,
                    "scout_role": concept.scout_role,
                    "scout_invocation_id": concept.source_invocation_id,
                    "composer_invocation_id": invocation.invocation_id,
                    "concept_relation_invocation_id": dedup_invocation.invocation_id,
                    "concept_evidence": concept.concise_evidence,
                    "concept_relation_evidence": dedup.concise_evidence,
                    "composer_evidence": output.concise_evidence,
                    "taxonomy_version_id": enrichment_brief.taxonomy_version_id,
                    "pipeline_version": "question-enrichment-v1",
                    "source_type": "de_novo",
                    "source_id": concept.concept_id,
                    "generating_system": "question-bank-multi-agent-pipeline",
                    "creator_invocation_id": invocation.invocation_id,
                    "parent_inputs": [concept.concept_id],
                    "rights_evidence": "project_generated_de_novo",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ), None

        with ThreadPoolExecutor(max_workers=max(1, min(16, len(approved)))) as pool:
            composed = list(pool.map(compose, approved)) if approved else []
        proposals = []
        for concept_id, proposal, error_type in composed:
            if proposal is None:
                failed_stage_items.append(f"composer:{concept_id}:{error_type}")
            else:
                proposals.append(proposal)
        return ProposalBatch(
            enrichment_brief.brief_id,
            approved,
            proposals,
            diverted,
            failed_stage_items,
        )

    @staticmethod
    def _concept_context(concept: CreativeConcept) -> Dict[str, str]:
        return {
            "concept_id": concept.concept_id,
            "summary": concept.summary,
            "aspect_id": concept.aspect_id,
            "perspective_id": concept.perspective_id,
            "semantic_scenario": concept.semantic_scenario,
            "answer_space": concept.answer_space,
            "taxonomy_status": concept.taxonomy_status,
        }


class ProposalEvaluation:
    """Independent specialist judges, relation judges, challenge, deterministic decision."""

    def __init__(self, runner: AgentRunner, neighbor_index: QuestionBankNeighborIndex, decider: AdmissionDecider) -> None:
        self._runner = runner
        self._neighbors = neighbor_index
        self._decider = decider

    def evaluate(self, question_proposal: QuestionProposal, evaluation_context: Dict[str, Any]) -> EvaluationResult:
        preflight = self._preflight(question_proposal)
        if preflight:
            evidence = EvaluationEvidence(
                f"evidence-{_stable_hash([question_proposal.proposal_id, preflight])[:20]}",
                question_proposal.proposal_id,
                True,
                preflight,
                [],
                False,
                [],
            )
            return EvaluationResult(evidence, self._decider.decide(question_proposal, evidence))
        proposal_payload = {
            "enrichment_run_id": question_proposal.provenance.get("enrichment_run_id", ""),
            "question": question_proposal.text,
            "level": question_proposal.level.value,
            "aspect_id": question_proposal.aspect_id,
            "perspective_id": question_proposal.perspective_id,
            "semantic_scenario": question_proposal.semantic_scenario,
            "answer_space": question_proposal.answer_space,
            "wording_pattern": question_proposal.wording_pattern,
            "source_permission": question_proposal.source_permission,
        }

        def judge(role: str) -> SpecialistJudgment:
            judge_payload = {
                "proposal": proposal_payload,
                "policy_version": evaluation_context.get("policy_version", "quality-v1"),
            }
            if role == "ontology_judge":
                judge_payload["taxonomy"] = evaluation_context.get(
                    "taxonomy_definitions",
                    {},
                )
            output, invocation = self._runner.invoke(
                role,
                "Judge only the question text under your named specialty. Do not simulate an answer or inspect peer verdicts.",
                judge_payload,
                JudgmentOutput,
                f"{role}-v1",
            )
            return SpecialistJudgment(
                f"judgment-{_stable_hash([question_proposal.proposal_id, role, invocation.output_hash])[:20]}",
                question_proposal.proposal_id,
                role,
                output.passed,
                output.uncertain,
                output.reason_codes,
                output.facet_values,
                invocation.invocation_id,
                output.concise_evidence,
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            judgments = list(pool.map(judge, ModelRouting.EVALUATION_ROLES))
        ontology = next(judgment for judgment in judgments if judgment.role == "ontology_judge")
        required_facets = {
            "aspect_id",
            "perspective_id",
            "semantic_scenario",
            "answer_space",
            "wording_pattern",
        }
        facet_uncertainty = []
        if not evaluation_context.get("taxonomy_definitions"):
            facet_uncertainty.append("missing_taxonomy_definitions")
        if set(ontology.facet_values) != required_facets:
            facet_uncertainty.append("incomplete_facet_classification")
        canonical_payload = {**proposal_payload, **ontology.facet_values}
        fingerprint = {
            "text": question_proposal.text,
            "scenario": ontology.facet_values.get("semantic_scenario", ""),
            "perspective_id": ontology.facet_values.get("perspective_id", ""),
            "answer_space": ontology.facet_values.get("answer_space", ""),
        }
        neighbors = self._neighbors.find_neighbors(fingerprint, evaluation_context["snapshot_id"])

        def relate(neighbor) -> NeighborRelation:
            output, invocation = self._runner.invoke(
                "neighbor_relation_judge",
                "A repeat requires substantial overlap in scenario, perspective, and answer space; one shared facet is insufficient.",
                {"candidate": canonical_payload, "neighbor": asdict(neighbor)},
                RelationOutput,
                "neighbor-relation-v1",
            )
            return NeighborRelation(
                f"relation-{_stable_hash([question_proposal.proposal_id, neighbor.neighbor_revision_id, invocation.output_hash])[:20]}", neighbor.neighbor_revision_id, output.semantic_repeat,
                output.uncertain, output.reason_codes, invocation.invocation_id,
                output.scenario_relation, output.perspective_relation, output.answer_space_relation,
                output.aspect_relation, output.wording_pattern_relation,
                output.concise_evidence,
            )

        with ThreadPoolExecutor(max_workers=max(1, min(12, len(neighbors)))) as pool:
            relations = list(pool.map(relate, neighbors)) if neighbors else []
        challenge, challenge_invocation = self._runner.invoke(
            "evidence_challenger",
            "Check that evidence is complete and surface material uncertainty. Do not overwrite prior judgments.",
            {
                "proposal": proposal_payload,
                "judgments": [asdict(judgment) for judgment in judgments],
                "relations": [asdict(relation) for relation in relations],
            },
            ChallengeOutput,
            "evidence-challenger-v1",
        )
        failures = sorted({reason for judgment in judgments if not judgment.passed and not judgment.uncertain for reason in judgment.reason_codes})
        uncertainties = sorted(
            {reason for judgment in judgments if judgment.uncertain for reason in judgment.reason_codes}
            | {reason for relation in relations if relation.uncertain for reason in relation.reason_codes}
            | set(challenge.uncertainty_reason_codes)
            | set(facet_uncertainty)
        )
        complete = challenge.complete and len(judgments) == 4
        semantic_judgments = [
            {key: value for key, value in asdict(judgment).items() if key != "invocation_id"}
            for judgment in judgments
        ]
        semantic_relations = [
            {key: value for key, value in asdict(relation).items() if key != "invocation_id"}
            for relation in relations
        ]
        evidence = EvaluationEvidence(
            f"evidence-{_stable_hash([question_proposal.proposal_id, semantic_judgments, semantic_relations, challenge.model_dump(mode='json')])[:20]}",
            question_proposal.proposal_id,
            complete,
            failures,
            uncertainties,
            any(relation.semantic_repeat for relation in relations),
            [judgment.invocation_id for judgment in judgments] + [relation.invocation_id for relation in relations] + [challenge_invocation.invocation_id],
            judgments,
            relations,
            challenge_invocation.invocation_id,
            ontology.facet_values,
        )
        return EvaluationResult(evidence, self._decider.decide(question_proposal, evidence))

    @staticmethod
    def _preflight(proposal: QuestionProposal) -> List[str]:
        failures = []
        text = proposal.text.strip()
        if not text or not text.endswith("?"):
            failures.append("not_a_question")
        if text.count("?") != 1:
            failures.append("not_single_question")
        if len(text.split()) < 4 or len(text) > 280:
            failures.append("invalid_question_length")
        if proposal.source_permission not in {"de_novo", "internal_licensed", "human_authored"}:
            failures.append("source_permission_denied")
        return failures


class ThemeClassifier:
    """Post-accept zero-to-many classification with an independent challenger."""

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def classify(
        self,
        proposal: QuestionProposal,
        named_themes: Sequence[str] | Mapping[str, Sequence[str]],
    ) -> ThemeClassification:
        definitions = (
            {theme: list(description) for theme, description in named_themes.items()}
            if isinstance(named_themes, Mapping)
            else {theme: [] for theme in named_themes}
        )
        payload = {
            "question": proposal.text,
            "named_theme_definitions": definitions,
            "empty_set_allowed": True,
        }
        first, first_invocation = self._runner.invoke(
            "theme_classifier",
            "Assign every direct equal membership. A confident empty set is valid; never assign Random.",
            payload,
            ThemeOutput,
            "theme-classifier-v1",
        )
        challenge, challenge_invocation = self._runner.invoke(
            "theme_classification_challenger",
            "Independently challenge memberships and return the resolved set you support.",
            {**payload, "proposed_memberships": first.memberships, "proposed_reason_codes": first.reason_codes},
            ThemeOutput,
            "theme-challenger-v1",
        )
        first_set = {theme for theme in first.memberships if theme.lower() != "random"}
        challenge_set = {theme for theme in challenge.memberships if theme.lower() != "random"}
        resolved = not first.uncertain and not challenge.uncertain and first_set == challenge_set
        uncertainties = [] if resolved else sorted(set(first.reason_codes + challenge.reason_codes + ["theme_classifier_disagreement"]))
        return ThemeClassification(
            f"themes-{_stable_hash([proposal.proposal_id, sorted(first_set), sorted(challenge_set)])[:20]}",
            proposal.proposal_id,
            sorted(first_set) if resolved else [],
            resolved,
            [first_invocation.invocation_id, challenge_invocation.invocation_id],
            uncertainties,
            [first.concise_evidence, challenge.concise_evidence],
        )


class TaxonomyAgentGroup:
    """Slower independent candidate-author, specialist, challenger, and shadow path."""

    SPECIALIST_ROLES = (
        "taxonomy_kind_judge",
        "taxonomy_distinctness_judge",
        "taxonomy_reusability_judge",
        "taxonomy_stability_judge",
        "taxonomy_variety_value_judge",
        "taxonomy_safety_neutrality_judge",
    )

    def __init__(
        self,
        runner: AgentRunner,
        registry: TaxonomyRegistry,
        bank: Optional[QuestionBank] = None,
        snapshot_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._bank = bank
        self._snapshot_provider = snapshot_provider

    def evaluate_gap(
        self,
        supporting_concepts: Sequence[CreativeConcept],
        current_taxonomy: Dict[str, Any],
        coverage_plan: Dict[str, Any],
    ) -> Tuple[TaxonomyCandidate, TaxonomyDecision]:
        support = [asdict(concept) for concept in supporting_concepts]
        authored, _ = self._runner.invoke(
            "taxonomy_candidate_author",
            "Name and define the repeated classification gap. Do not decide whether it is accepted.",
            {"supporting_concepts": support, "current_taxonomy": current_taxonomy},
            TaxonomyCandidateOutput,
            "taxonomy-author-v1",
        )
        candidate_id = f"taxonomy-candidate-{_stable_hash([support, authored.model_dump()])[:20]}"
        candidate = TaxonomyCandidate(
            candidate_id,
            f"taxonomy-candidate-key-{candidate_id}",
            authored.facet,
            authored.label,
            authored.definition,
            [concept.concept_id for concept in supporting_concepts],
            authored.aliases,
            authored.exclusions,
            authored.positive_examples,
            authored.counterexamples,
            authored.closest_existing_taxa,
            authored.explicit_differences,
            authored.affected_taxon_ids,
            authored.proposed_operation,
            concise_evidence=authored.concise_evidence,
            replacement_taxa=[
                taxon.model_dump(mode="json") for taxon in authored.replacement_taxa
            ],
        )
        candidate_payload = asdict(candidate)

        def judge(role: str):
            return self._runner.invoke(
                role,
                "Judge the proposed taxonomy definition independently under your named specialty.",
                {"candidate": candidate_payload, "support": support, "current_taxonomy": current_taxonomy, "coverage_plan": coverage_plan},
                JudgmentOutput,
                f"{role}-v1",
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            specialist_runs = list(pool.map(judge, self.SPECIALIST_ROLES))
        specialists = [item[0] for item in specialist_runs]
        challenger, challenger_invocation = self._runner.invoke(
            "taxonomy_challenger",
            "Try to absorb the candidate into existing terms and find counterexamples or facet confusion.",
            {
                "candidate": candidate_payload,
                "specialist_reason_codes": [output.reason_codes for output in specialists],
                "current_taxonomy": current_taxonomy,
                "support": support,
            },
            JudgmentOutput,
            "taxonomy-challenger-v1",
        )

        current_questions = []
        if self._bank is not None and self._snapshot_provider is not None:
            current_snapshot_id = self._snapshot_provider()
            if current_snapshot_id:
                current_questions = [
                    {
                        "question": revision.text,
                        "aspect_id": revision.aspect_id,
                        "perspective_id": revision.perspective_id,
                    }
                    for revision in self._bank.list_revisions(current_snapshot_id)
                ]
        taxonomy_examples = []
        for facet in ("aspects", "perspectives"):
            for taxon in current_taxonomy.get(facet, []):
                if isinstance(taxon, dict):
                    taxonomy_examples.extend(taxon.get("positive_examples", []))
                    taxonomy_examples.extend(taxon.get("counterexamples", []))
        mixed_examples = sorted(
            [
                *({"kind": "support", "value": item} for item in support),
                *(
                    {"kind": "current_question", "value": item}
                    for item in current_questions
                ),
                *(
                    {"kind": "neighbor_taxon_example", "value": item}
                    for item in taxonomy_examples
                ),
                *(
                    {"kind": "candidate_counterexample", "value": item}
                    for item in candidate.counterexamples
                ),
            ],
            key=_stable_hash,
        )

        def shadow(index: int):
            return self._runner.invoke(
                f"taxonomy_shadow_classifier_{index}",
                "Apply the hidden definition to the mixed examples independently; pass only for stable classification.",
                {
                    "definition": candidate.definition,
                    "mixed_examples": mixed_examples,
                    "current_taxonomy": current_taxonomy,
                },
                JudgmentOutput,
                "taxonomy-shadow-v1",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            shadow_runs = list(pool.map(shadow, (1, 2)))
        shadows = [item[0] for item in shadow_runs]
        candidate.independent_evidence = [
            {
                "role": role,
                "invocation_id": invocation.invocation_id,
                "passed": output.passed,
                "uncertain": output.uncertain,
                "reason_codes": output.reason_codes,
                "concise_evidence": output.concise_evidence,
            }
            for role, (output, invocation) in zip(
                self.SPECIALIST_ROLES, specialist_runs, strict=True
            )
        ] + [
            {
                "role": "taxonomy_challenger",
                "invocation_id": challenger_invocation.invocation_id,
                "passed": challenger.passed,
                "uncertain": challenger.uncertain,
                "reason_codes": challenger.reason_codes,
                "concise_evidence": challenger.concise_evidence,
            }
        ] + [
            {
                "role": f"taxonomy_shadow_classifier_{index}",
                "invocation_id": invocation.invocation_id,
                "passed": output.passed,
                "uncertain": output.uncertain,
                "reason_codes": output.reason_codes,
                "concise_evidence": output.concise_evidence,
            }
            for index, (output, invocation) in enumerate(shadow_runs, start=1)
        ]
        affected_verified = self._prepare_affected_reclassification(
            candidate, current_taxonomy
        )
        context = {
            "specialists_passed": all(output.passed and not output.uncertain for output in specialists),
            "challenger_passed": challenger.passed and not challenger.uncertain,
            "shadow_agreement": sum(output.passed and not output.uncertain for output in shadows),
            "distinct_scenarios": len({concept.semantic_scenario for concept in supporting_concepts}),
            "distinct_perspectives": len({concept.perspective_id for concept in supporting_concepts}),
            "distinct_aspects": len({concept.aspect_id for concept in supporting_concepts}),
            "distinct_answer_spaces": len({concept.answer_space for concept in supporting_concepts}),
            "distinct_scouts": len({concept.scout_role for concept in supporting_concepts}),
            "distinct_briefs": len({concept.brief_id for concept in supporting_concepts}),
            "affected_reclassification_verified": affected_verified,
        }
        decision = self._registry.evaluate_candidate(candidate, context)
        if affected_verified and candidate.proposed_operation in {
            "merge",
            "split",
            "rename",
            "deprecate",
        }:
            self._registry.attach_verified_change_package(
                candidate.candidate_id,
                {
                    "affected_revision_ids": candidate.affected_revision_ids,
                    "reclassification_plan": candidate.reclassification_plan,
                    "revalidation_evidence_ids": candidate.revalidation_evidence_ids,
                    "material_definition_change": self._material_definition_change(
                        candidate, current_taxonomy
                    ),
                },
            )
        return candidate, decision

    @staticmethod
    def _material_definition_change(
        candidate: TaxonomyCandidate, current_taxonomy: Dict[str, Any]
    ) -> bool:
        if candidate.proposed_operation != "rename":
            return candidate.proposed_operation in {"merge", "split", "deprecate"}
        facet_key = "aspects" if candidate.facet == "aspect" else "perspectives"
        definitions = {
            taxon.get("id"): taxon.get("definition")
            for taxon in current_taxonomy.get(facet_key, [])
            if isinstance(taxon, dict)
        }
        return any(
            definitions.get(taxon_id) != candidate.definition
            for taxon_id in candidate.affected_taxon_ids
        )

    def _prepare_affected_reclassification(
        self, candidate: TaxonomyCandidate, current_taxonomy: Dict[str, Any]
    ) -> bool:
        if candidate.proposed_operation not in {
            "merge",
            "split",
            "rename",
            "deprecate",
        }:
            return True
        if self._bank is None or self._snapshot_provider is None:
            return False
        snapshot_id = self._snapshot_provider()
        revisions = self._bank.list_revisions(snapshot_id) if snapshot_id else []
        facet_name = "aspect_id" if candidate.facet == "aspect" else "perspective_id"
        projection = current_taxonomy.get("classification_projection", {})
        projected_key = "aspect" if candidate.facet == "aspect" else "perspective"
        affected = []
        for revision in revisions:
            original_taxon_id = getattr(revision, facet_name)
            current_taxon_id = projection.get(revision.revision_id, {}).get(
                projected_key, original_taxon_id
            )
            if current_taxon_id in set(candidate.affected_taxon_ids):
                affected.append(revision)
        if candidate.proposed_operation == "split":
            allowed_targets = {
                item["label"].strip().lower().replace(" ", "_")
                for item in candidate.replacement_taxa
            }
            if len(allowed_targets) < 2:
                return False
        elif candidate.proposed_operation == "rename":
            allowed_targets = set(candidate.affected_taxon_ids)
        else:
            allowed_targets = {
                candidate.label.strip().lower().replace(" ", "_")
            }
        plan: Dict[str, str] = {}
        invocation_ids: List[str] = []
        for revision in affected:
            payload = {
                "revision": record_dict(revision),
                "candidate": record_dict(candidate),
                "allowed_target_taxon_ids": sorted(allowed_targets),
            }

            def classify(index: int, payload=payload):
                return self._runner.invoke(
                    f"taxonomy_affected_revision_classifier_{index}",
                    "Reclassify this affected revision. Put exactly one allowed target in facet_values.target_taxon_id; abstain if ambiguous.",
                    payload,
                    JudgmentOutput,
                    "taxonomy-affected-reclassification-v1",
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                classified = list(pool.map(classify, (1, 2)))
            outputs = [item[0] for item in classified]
            invocation_ids.extend(item[1].invocation_id for item in classified)
            candidate.independent_evidence.extend(
                {
                    "role": f"taxonomy_affected_revision_classifier_{index}",
                    "revision_id": revision.revision_id,
                    "invocation_id": invocation.invocation_id,
                    "passed": output.passed,
                    "uncertain": output.uncertain,
                    "reason_codes": output.reason_codes,
                    "concise_evidence": output.concise_evidence,
                }
                for index, (output, invocation) in enumerate(classified, start=1)
            )
            targets = {
                output.facet_values.get("target_taxon_id", "") for output in outputs
            }
            if (
                any(not output.passed or output.uncertain for output in outputs)
                or len(targets) != 1
                or not targets.issubset(allowed_targets)
            ):
                candidate.affected_revision_ids = sorted(
                    [*plan, revision.revision_id]
                )
                candidate.revalidation_evidence_ids = sorted(invocation_ids)
                return False
            plan[revision.revision_id] = targets.pop()
        candidate.affected_revision_ids = sorted(plan)
        candidate.reclassification_plan = plan
        candidate.revalidation_evidence_ids = sorted(invocation_ids)
        return True


class ReleaseRevalidator:
    """Fresh GPT quality and whole-bank relation checks over a frozen candidate."""

    def __init__(
        self,
        runner: AgentRunner,
        neighbor_index: QuestionBankNeighborIndex,
        taxonomy_context_provider: Callable[[str], Dict[str, Any]],
        theme_definitions: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        self._runner = runner
        self._neighbors = neighbor_index
        self._taxonomy_context_provider = taxonomy_context_provider
        self._theme_definitions = dict(theme_definitions or {})

    def revalidate(self, revisions, packages, snapshot_id: str, intent: Dict[str, Any]):
        taxonomy = self._taxonomy_context_provider(intent["taxonomy_version_id"])

        def quality(revision):
            projected = taxonomy.get("classification_projection", {}).get(
                revision.revision_id, {}
            )
            proposal = {
                "snapshot_id": snapshot_id,
                "question": revision.text,
                "level": revision.level,
                "aspect_id": projected.get("aspect", revision.aspect_id),
                "perspective_id": projected.get(
                    "perspective", revision.perspective_id
                ),
                "semantic_scenario": revision.semantic_scenario,
                "answer_space": revision.answer_space,
                "wording_pattern": revision.wording_pattern,
            }

            def judge(role: str):
                payload = {"proposal": proposal, "policy_versions": intent["policy_versions"]}
                if role == "ontology_judge":
                    payload["taxonomy"] = taxonomy
                return self._runner.invoke(
                    role,
                    "Revalidate this frozen Question Revision independently for release.",
                    payload,
                    JudgmentOutput,
                    f"release-{role}-v1",
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                judged = list(pool.map(judge, ModelRouting.EVALUATION_ROLES))
            judgments = [item[0] for item in judged]
            invocation_ids = [item[1].invocation_id for item in judged]
            challenge, challenge_invocation = self._runner.invoke(
                "evidence_challenger",
                "Challenge the complete frozen release evidence without changing prior judgments.",
                {
                    "proposal": proposal,
                    "judgments": [result.model_dump(mode="json") for result in judgments],
                },
                ChallengeOutput,
                "release-evidence-challenger-v1",
            )
            return (
                all(result.passed and not result.uncertain for result in judgments)
                and challenge.complete
                and not challenge.uncertainty_reason_codes,
                invocation_ids + [challenge_invocation.invocation_id],
            )

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(revisions)))) as pool:
            quality_results = list(pool.map(quality, revisions)) if revisions else []

        # Release validation is intentionally exhaustive. Online evaluation may
        # retrieve a bounded neighbor set, but no candidate-bank pair is skipped
        # at the trust boundary.
        pairs = list(combinations(revisions, 2))

        def relation(pair):
            left, right = pair
            output, invocation = self._runner.invoke(
                "neighbor_relation_judge",
                "Revalidate all five facet relations. A repeat needs substantial Scenario, Perspective, and Answer Space overlap.",
                {"candidate": record_dict(left), "neighbor": record_dict(right)},
                RelationOutput,
                "release-neighbor-relation-v1",
            )
            return (
                not output.semantic_repeat and not output.uncertain,
                invocation.invocation_id,
            )

        with ThreadPoolExecutor(max_workers=max(1, min(12, len(pairs)))) as pool:
            relation_results = list(pool.map(relation, pairs)) if pairs else []

        def classify_theme(revision):
            payload = {
                "question": revision.text,
                "named_theme_definitions": self._theme_definitions,
                "empty_set_allowed": True,
            }
            first, first_invocation = self._runner.invoke(
                "theme_classifier",
                "Freshly reclassify this frozen revision for release.",
                payload,
                ThemeOutput,
                "release-theme-classifier-v1",
            )
            challenge, challenge_invocation = self._runner.invoke(
                "theme_classification_challenger",
                "Independently challenge the release theme memberships.",
                {**payload, "proposed_memberships": first.memberships},
                ThemeOutput,
                "release-theme-challenger-v1",
            )
            expected = set(revision.theme_memberships)
            first_set = {item for item in first.memberships if item.lower() != "random"}
            challenge_set = {
                item for item in challenge.memberships if item.lower() != "random"
            }
            return (
                not first.uncertain
                and not challenge.uncertain
                and first_set == challenge_set == expected,
                [first_invocation.invocation_id, challenge_invocation.invocation_id],
            )

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(revisions)))) as pool:
            theme_results = list(pool.map(classify_theme, revisions)) if revisions else []
        invocation_ids = [
            invocation_id
            for _, ids in quality_results
            for invocation_id in ids
        ] + [invocation_id for _, invocation_id in relation_results] + [
            invocation_id for _, ids in theme_results for invocation_id in ids
        ]
        gates = {
            "quality_revalidation": bool(quality_results)
            and all(passed for passed, _ in quality_results),
            "whole_bank_relation_revalidation": all(
                passed for passed, _ in relation_results
            ),
            "whole_bank_theme_revalidation": bool(theme_results)
            and all(passed for passed, _ in theme_results),
        }
        return {
            "gates": gates,
            "invocation_ids": invocation_ids,
            "evidence_hash": _stable_hash(
                {
                    "snapshot_id": snapshot_id,
                    "gates": gates,
                    "invocation_ids": invocation_ids,
                }
            ),
        }


class ReferenceRegressionEvaluator:
    """Run confirmed examples through the current independent GPT topology."""

    def __init__(
        self, runner: AgentRunner, registry: ReferenceExampleRegistry
    ) -> None:
        self._runner = runner
        self._registry = registry

    def run(
        self,
        policy_versions: Dict[str, str],
        taxonomy_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        examples = self._registry.confirmed_examples()
        results: Dict[str, bool] = {}
        invocation_ids: List[str] = []
        for example in examples:
            payload = {
                "proposal": {
                    "question": example["question"],
                    "level": example.get("level", "shallow"),
                    "aspect_id": example.get("aspect_id", "reference_aspect"),
                    "perspective_id": example.get("perspective_id", "reference_perspective"),
                    "semantic_scenario": example.get("semantic_scenario", "reference_scenario"),
                    "answer_space": example.get("answer_space", "reference_answer_space"),
                    "wording_pattern": example.get("wording_pattern", "reference_pattern"),
                    "source_permission": "human_authored",
                },
                "policy_versions": policy_versions,
            }

            def judge(role: str, payload=payload):
                judge_payload = dict(payload)
                if role == "ontology_judge" and taxonomy_context:
                    judge_payload["taxonomy"] = taxonomy_context
                return self._runner.invoke(
                    role,
                    "Apply the current production rubric to this human-confirmed Reference Example independently.",
                    judge_payload,
                    JudgmentOutput,
                    f"reference-{role}-v1",
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                judged = list(pool.map(judge, ModelRouting.EVALUATION_ROLES))
            judgments = [item[0] for item in judged]
            invocation_ids.extend(item[1].invocation_id for item in judged)
            relation = None
            if "neighbor_question" in example:
                relation, relation_invocation = self._runner.invoke(
                    "neighbor_relation_judge",
                    "Classify all five facet relations without seeing the expected benchmark result.",
                    {
                        "candidate": {"question": example["question"]},
                        "neighbor": {"question": example["neighbor_question"]},
                        "policy_versions": policy_versions,
                    },
                    RelationOutput,
                    "reference-neighbor-relation-v1",
                )
                invocation_ids.append(relation_invocation.invocation_id)
            challenge, challenge_invocation = self._runner.invoke(
                "evidence_challenger",
                "Challenge the Reference Example judgments and flag any unresolved evidence.",
                {
                    **payload,
                    "judgments": [judgment.model_dump(mode="json") for judgment in judgments],
                    "relations": [relation.model_dump(mode="json")] if relation else [],
                },
                ChallengeOutput,
                "reference-evidence-challenger-v1",
            )
            invocation_ids.append(challenge_invocation.invocation_id)
            if (
                any(judgment.uncertain for judgment in judgments)
                or bool(relation and relation.uncertain)
                or not challenge.complete
                or challenge.uncertainty_reason_codes
            ):
                predicted = "human_review"
            elif all(judgment.passed for judgment in judgments) and not (
                relation and relation.semantic_repeat
            ):
                predicted = "accept"
            else:
                predicted = "reject"
            quality_matches = predicted == example["expected_decision"]
            relation_matches = True
            if relation is not None:
                relation_matches = (
                    relation.semantic_repeat
                    == bool(example["expected_semantic_repeat"])
                    and not relation.uncertain
                )
            results[example["example_id"]] = quality_matches and relation_matches
        taxonomy_version_id = (
            str(taxonomy_context.get("version_id", "")) if taxonomy_context else ""
        )
        return self._registry.record_regression(
            policy_versions, results, taxonomy_version_id, invocation_ids
        )


class CoveragePlanAgentGroup:
    """Two isolated GPT classifiers plus a challenger for every region."""

    def __init__(
        self,
        runner: AgentRunner,
        planner: CoveragePlanner,
        review: HumanReview,
    ) -> None:
        self._runner = runner
        self._planner = planner
        self._review = review

    def generate(
        self,
        taxonomy_context: Dict[str, Any],
        theme_definitions: Mapping[str, Sequence[str]],
    ) -> Dict[str, Any]:
        regions = []
        region_records = []
        review_case_ids = []
        draft_id = f"coverage-draft-{_stable_hash(taxonomy_context['version_id'])[:20]}"
        aspects = taxonomy_context["aspects"]
        perspectives = taxonomy_context["perspectives"]
        for theme, theme_definition in theme_definitions.items():
            for level in ("shallow", "deep"):
                for aspect in aspects:
                    for perspective in perspectives:
                        payload = {
                            "theme": {"id": theme, "definition": list(theme_definition)},
                            "level": level,
                            "aspect": aspect,
                            "perspective": perspective,
                        }

                        def classify(index: int, payload=payload):
                            return self._runner.invoke(
                                f"coverage_region_classifier_{index}",
                                "Classify the region as required, exploratory, or invalid. Abstain when uncertain.",
                                payload,
                                CoverageRegionOutput,
                                "coverage-region-classifier-v1",
                            )[0]

                        with ThreadPoolExecutor(max_workers=2) as pool:
                            first, second = pool.map(classify, (1, 2))
                        challenge, _ = self._runner.invoke(
                            "coverage_region_challenger",
                            "Challenge artificial Required regions and find plausible examples for Invalid regions.",
                            {
                                **payload,
                                "classifications": [
                                    first.model_dump(mode="json"),
                                    second.model_dump(mode="json"),
                                ],
                            },
                            CoverageRegionOutput,
                            "coverage-region-challenger-v1",
                        )
                        region_id = "region-" + _stable_hash(payload)[:20]
                        if (
                            first.uncertain
                            or second.uncertain
                            or challenge.uncertain
                            or len({first.kind, second.kind, challenge.kind}) != 1
                        ):
                            case = self._review.open_case(
                                ReviewRequest(
                                    f"coverage-request-{region_id}",
                                    f"coverage-review-{taxonomy_context['version_id']}-{region_id}",
                                    "coverage_region",
                                    region_id,
                                    {
                                        **payload,
                                        "draft_id": draft_id,
                                        "region_id": region_id,
                                        "taxonomy_version_id": taxonomy_context["version_id"],
                                        "classifications": [
                                            first.model_dump(mode="json"),
                                            second.model_dump(mode="json"),
                                            challenge.model_dump(mode="json"),
                                        ],
                                    },
                                )
                            )
                            review_case_ids.append(case.case_id)
                            region_records.append(
                                {
                                    "region_id": region_id,
                                    "theme_id": theme,
                                    "level": level,
                                    "aspect_id": aspect["id"],
                                    "perspective_id": perspective["id"],
                                    "kind": None,
                                    "minimum_distinct_scenarios": 3,
                                }
                            )
                            continue
                        region = CoverageRegion(
                                region_id,
                                theme,
                                QuestionLevel(level),
                                aspect["id"],
                                perspective["id"],
                                first.kind,
                            )
                        regions.append(region)
                        region_records.append(record_dict(region))
        if review_case_ids:
            self._planner.save_draft(
                draft_id, taxonomy_context["version_id"], region_records
            )
            return {
                "status": "human_review",
                "draft_id": draft_id,
                "review_case_ids": review_case_ids,
            }
        plan = self._planner.plan(
            {"version_id": taxonomy_context["version_id"], "regions": regions}
        )
        return {"status": "planned", "coverage_plan": record_dict(plan)}
