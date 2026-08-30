"""Isolated, structured LLM agent groups for autonomous enrichment."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple, Type

from pydantic import BaseModel, Field

from models import resolve_llm_model
from question_bank.contracts import (
    AgentInvocation,
    CreativeConcept,
    EnrichmentBrief,
    EvaluationEvidence,
    EvaluationResult,
    NeighborRelation,
    ProposalBatch,
    QuestionProposal,
    SpecialistJudgment,
    TaxonomyCandidate,
    TaxonomyDecision,
    ThemeClassification,
    record_dict,
)
from question_bank.core import AdmissionDecider, _stable_hash
from question_bank.modules import QuestionBankNeighborIndex, TaxonomyRegistry
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


class ConceptBatchOutput(BaseModel):
    concepts: List[ConceptOutput]


class ConceptDedupOutput(BaseModel):
    keep_concept_ids: List[str] = Field(default_factory=list)


class ProposalOutput(BaseModel):
    question: str
    wording_pattern: str


class JudgmentOutput(BaseModel):
    passed: bool
    uncertain: bool
    reason_codes: List[str]
    facet_values: Dict[str, str] = Field(default_factory=dict)


class RelationOutput(BaseModel):
    semantic_repeat: bool
    uncertain: bool
    reason_codes: List[str]
    scenario_relation: str
    perspective_relation: str
    answer_space_relation: str
    aspect_relation: str
    wording_pattern_relation: str


class ChallengeOutput(BaseModel):
    complete: bool
    uncertainty_reason_codes: List[str]


class ThemeOutput(BaseModel):
    memberships: List[str]
    uncertain: bool
    reason_codes: List[str]


class TaxonomyCandidateOutput(BaseModel):
    facet: str
    label: str
    definition: str
    aliases: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)


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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._db.commit()
        self._lock = threading.Lock()
        self._llm_factory = llm_factory
        self.routing = routing or ModelRouting()
        self.execution_version = execution_version

    def close(self) -> None:
        self._db.close()

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
        messages = [
            {
                "role": "system",
                "content": (
                    f"ROLE: {role}\n{instructions}\n"
                    "Return only the requested structured result. Give concise reason codes, never private chain-of-thought."
                ),
            },
            {"role": "user", "content": json.dumps(payload, sort_keys=True, ensure_ascii=False)},
        ]
        input_hash = _stable_hash(messages)
        failure: Optional[Exception] = None
        output: Optional[BaseModel] = None
        for _ in range(2):
            try:
                output = self._llm_factory(preset).parse_structured(messages, response_model)
                break
            except Exception as error:  # external boundary; one policy-approved execution retry
                failure = error
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
            )
            raise RuntimeError(f"agent stage {role} failed after one retry") from failure
        output_payload = output.model_dump(mode="json")
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
            output_hash=_stable_hash(output_payload),
            status="succeeded",
            concise_reason_codes=list(output_payload.get("reason_codes", [])),
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
        self._persist(invocation, messages, output_payload, configuration)
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
    ):
        invocation = AgentInvocation(
            f"inv-{uuid.uuid4().hex}", role, provider, preset, provider_model, reasoning, prompt_version, 1,
            context_policy_version, self.execution_version, input_hash, "", "failed", ["execution_failed_after_retry"],
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
                "INSERT INTO agent_invocations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
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
            return role, self._runner.invoke(
                role,
                f"{missions[role]} Develop distinct concepts; do not write final questions.",
                payload,
                ConceptBatchOutput,
                "proposal-scout-v1",
            )

        concepts: List[CreativeConcept] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for role, (result, _) in pool.map(scout, ModelRouting.SCOUT_ROLES):
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
                        )
                    )
        approved = [concept for concept in concepts if concept.taxonomy_status == "approved"]
        diverted = [concept for concept in concepts if concept.taxonomy_status != "approved"]
        dedup, dedup_invocation = self._runner.invoke(
            "concept_relation_judge",
            "Identify concepts that substantially repeat scenario, perspective, and answer space. Keep distinct concepts.",
            {"concepts": [asdict(concept) for concept in approved]},
            ConceptDedupOutput,
            "concept-relation-v1",
        )
        keep = set(dedup.keep_concept_ids)
        approved = [concept for concept in approved if concept.concept_id in keep]

        def compose(concept: CreativeConcept) -> QuestionProposal:
            output, invocation = self._runner.invoke(
                "composer",
                "Write exactly one understandable, bounded-open question. Output only the question and its wording pattern.",
                {"level": enrichment_brief.level.value, "concept": asdict(concept)},
                ProposalOutput,
                "composer-v1",
            )
            proposal_id = f"proposal-{_stable_hash([concept.concept_id, output.question])[:20]}"
            return QuestionProposal(
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
                    "concept_id": concept.concept_id,
                    "scout_role": concept.scout_role,
                    "composer_invocation_id": invocation.invocation_id,
                    "concept_relation_invocation_id": dedup_invocation.invocation_id,
                },
            )

        with ThreadPoolExecutor(max_workers=max(1, min(16, len(approved)))) as pool:
            proposals = list(pool.map(compose, approved)) if approved else []
        return ProposalBatch(enrichment_brief.brief_id, approved, proposals, diverted)


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
        proposal_payload = asdict(question_proposal)
        proposal_payload["level"] = question_proposal.level.value

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
                f"judgment-{uuid.uuid4().hex}",
                question_proposal.proposal_id,
                role,
                output.passed,
                output.uncertain,
                output.reason_codes,
                output.facet_values,
                invocation.invocation_id,
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
                f"relation-{uuid.uuid4().hex}", neighbor.neighbor_revision_id, output.semantic_repeat,
                output.uncertain, output.reason_codes, invocation.invocation_id,
                output.scenario_relation, output.perspective_relation, output.answer_space_relation,
                output.aspect_relation, output.wording_pattern_relation,
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
        evidence = EvaluationEvidence(
            f"evidence-{_stable_hash([question_proposal.proposal_id, [asdict(j) for j in judgments], [asdict(r) for r in relations]])[:20]}",
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

    def classify(self, proposal: QuestionProposal, named_themes: Sequence[str]) -> ThemeClassification:
        payload = {"question": proposal.text, "named_themes": list(named_themes), "empty_set_allowed": True}
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

    def __init__(self, runner: AgentRunner, registry: TaxonomyRegistry) -> None:
        self._runner = runner
        self._registry = registry

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
        )
        candidate_payload = asdict(candidate)

        def judge(role: str):
            return self._runner.invoke(
                role,
                "Judge the proposed taxonomy definition independently under your named specialty.",
                {"candidate": candidate_payload, "support": support, "current_taxonomy": current_taxonomy, "coverage_plan": coverage_plan},
                JudgmentOutput,
                f"{role}-v1",
            )[0]

        with ThreadPoolExecutor(max_workers=6) as pool:
            specialists = list(pool.map(judge, self.SPECIALIST_ROLES))
        challenger, _ = self._runner.invoke(
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

        def shadow(index: int):
            return self._runner.invoke(
                f"taxonomy_shadow_classifier_{index}",
                "Apply the hidden definition to the mixed examples independently; pass only for stable classification.",
                {"definition": candidate.definition, "support": support, "current_taxonomy": current_taxonomy},
                JudgmentOutput,
                "taxonomy-shadow-v1",
            )[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            shadows = list(pool.map(shadow, (1, 2)))
        context = {
            "specialists_passed": all(output.passed and not output.uncertain for output in specialists),
            "challenger_passed": challenger.passed and not challenger.uncertain,
            "shadow_agreement": sum(output.passed and not output.uncertain for output in shadows),
        }
        return candidate, self._registry.evaluate_candidate(candidate, context)


class ReleaseRevalidator:
    """Fresh GPT quality and whole-bank relation checks over a frozen candidate."""

    def __init__(
        self,
        runner: AgentRunner,
        neighbor_index: QuestionBankNeighborIndex,
        taxonomy_context_provider: Callable[[str], Dict[str, Any]],
    ) -> None:
        self._runner = runner
        self._neighbors = neighbor_index
        self._taxonomy_context_provider = taxonomy_context_provider

    def revalidate(self, revisions, packages, snapshot_id: str, intent: Dict[str, Any]):
        taxonomy = self._taxonomy_context_provider(intent["taxonomy_version_id"])

        def quality(revision) -> bool:
            proposal = {
                "question": revision.text,
                "level": revision.level,
                "aspect_id": revision.aspect_id,
                "perspective_id": revision.perspective_id,
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
                )[0]

            with ThreadPoolExecutor(max_workers=4) as pool:
                judgments = list(pool.map(judge, ModelRouting.EVALUATION_ROLES))
            challenge, _ = self._runner.invoke(
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
                and not challenge.uncertainty_reason_codes
            )

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(revisions)))) as pool:
            quality_results = list(pool.map(quality, revisions)) if revisions else []

        revision_by_id = {revision.revision_id: revision for revision in revisions}
        pairs = {}
        for revision in revisions:
            fingerprint = {
                "text": revision.text,
                "scenario": revision.semantic_scenario,
                "perspective_id": revision.perspective_id,
                "answer_space": revision.answer_space,
            }
            for neighbor in self._neighbors.find_neighbors(fingerprint, snapshot_id):
                if neighbor.neighbor_revision_id == revision.revision_id:
                    continue
                pair_key = tuple(sorted((revision.revision_id, neighbor.neighbor_revision_id)))
                pairs[pair_key] = (revision, revision_by_id[neighbor.neighbor_revision_id])

        def relation(pair) -> bool:
            left, right = pair
            output, _ = self._runner.invoke(
                "neighbor_relation_judge",
                "Revalidate all five facet relations. A repeat needs substantial Scenario, Perspective, and Answer Space overlap.",
                {"candidate": record_dict(left), "neighbor": record_dict(right)},
                RelationOutput,
                "release-neighbor-relation-v1",
            )
            return not output.semantic_repeat and not output.uncertain

        with ThreadPoolExecutor(max_workers=max(1, min(12, len(pairs)))) as pool:
            relation_results = list(pool.map(relation, pairs.values())) if pairs else []
        return {
            "quality_revalidation": bool(quality_results) and all(quality_results),
            "whole_bank_relation_revalidation": all(relation_results),
        }
