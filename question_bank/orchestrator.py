"""Autonomous, fail-closed orchestration over one fixed bank snapshot."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Callable, Dict, Sequence

from question_bank.agents import ProposalEvaluation, ProposalProduction, ThemeClassifier
from question_bank.contracts import (
    AcceptedQuestionPackage,
    AdmissionDecision,
    AdmissionOutcome,
    CreativeConcept,
    EnrichmentBrief,
    EnrichmentRunResult,
    EvaluationEvidence,
    HumanResolution,
    QuestionLevel,
    QuestionProposal,
    ReviewRequest,
    ThemeClassification,
    record_dict,
)
from question_bank.core import QuestionBank, _stable_hash
from question_bank.modules import HumanReview


class PipelineOrchestrator:
    """Orders modules, persists evidence, and is idempotent at brief/run level."""

    def __init__(
        self,
        database_path: Path | str,
        proposal_production: ProposalProduction,
        proposal_evaluation: ProposalEvaluation,
        theme_classifier: ThemeClassifier,
        question_bank: QuestionBank,
        human_review: HumanReview,
        named_themes: Sequence[str],
        taxonomy_context_provider: Callable[[str], Dict] | None = None,
    ) -> None:
        self._db = sqlite3.connect(str(database_path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS enrichment_runs (
                run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, brief_json TEXT NOT NULL,
                fixed_snapshot_id TEXT NOT NULL, result_json TEXT, status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creative_concepts (
                concept_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluation_evidence (
                evidence_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admission_outcomes (
                outcome_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS theme_classifications (
                classification_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS taxonomy_concept_queue (
                concept_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS taxonomy_concept_consumptions (
                concept_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()
        self._proposal = proposal_production
        self._evaluation = proposal_evaluation
        self._themes = theme_classifier
        self._bank = question_bank
        self._review = human_review
        self._named_themes = list(named_themes)
        self._taxonomy_context_provider = taxonomy_context_provider or (
            lambda version_id: {
                "version_id": version_id,
                "aspects": [],
                "perspectives": [],
            }
        )

    def close(self) -> None:
        self._db.close()

    def run_enrichment(self, enrichment_brief: EnrichmentBrief) -> EnrichmentRunResult:
        existing = self._db.execute(
            "SELECT result_json FROM enrichment_runs WHERE idempotency_key = ? AND status = 'completed'",
            (enrichment_brief.idempotency_key,),
        ).fetchone()
        if existing:
            return self._result(json.loads(existing[0]))
        run_id = f"run-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT INTO enrichment_runs VALUES (?, ?, ?, ?, NULL, 'running', CURRENT_TIMESTAMP)",
                (
                    run_id,
                    enrichment_brief.idempotency_key,
                    json.dumps(record_dict(enrichment_brief), sort_keys=True),
                    enrichment_brief.snapshot_id,
                ),
            )
        accepted = []
        rejected = []
        reviews = []
        batch = self._proposal.propose(enrichment_brief)
        with self._db:
            for concept in batch.concepts + batch.diverted_taxonomy_concepts:
                self._db.execute(
                    "INSERT OR IGNORE INTO creative_concepts VALUES (?, ?, ?)",
                    (concept.concept_id, run_id, json.dumps(record_dict(concept), sort_keys=True)),
                )
            for concept in batch.diverted_taxonomy_concepts:
                self._db.execute(
                    "INSERT OR IGNORE INTO taxonomy_concept_queue VALUES (?, ?, ?)",
                    (concept.concept_id, run_id, json.dumps(record_dict(concept), sort_keys=True)),
                )
        for proposal in batch.proposals:
            self._persist_proposal(run_id, proposal)
            try:
                evaluation = self._evaluation.evaluate(
                    proposal,
                    {
                        "snapshot_id": enrichment_brief.snapshot_id,
                        "taxonomy_version_id": enrichment_brief.taxonomy_version_id,
                        "taxonomy_definitions": self._taxonomy_context_provider(
                            enrichment_brief.taxonomy_version_id
                        ),
                    },
                )
            except Exception as error:
                request = ReviewRequest(
                    f"request-{uuid.uuid4().hex}",
                    f"stage-failure-{run_id}-{proposal.proposal_id}",
                    "admission",
                    proposal.proposal_id,
                    {
                        "question": proposal.text,
                        "reason_codes": ["stage_failed_after_retry"],
                        "stage_error_type": type(error).__name__,
                        "proposal": record_dict(proposal),
                        "snapshot_id": enrichment_brief.snapshot_id,
                        "taxonomy_version_id": enrichment_brief.taxonomy_version_id,
                    },
                )
                reviews.append(self._review.open_case(request).case_id)
                continue
            self._persist_evaluation(evaluation)
            if evaluation.outcome.decision == AdmissionDecision.REJECT:
                rejected.append(proposal.proposal_id)
                continue
            if evaluation.outcome.decision == AdmissionDecision.HUMAN_REVIEW:
                reviews.append(
                    self._open_admission_review(
                        proposal,
                        evaluation,
                        enrichment_brief.snapshot_id,
                        enrichment_brief.taxonomy_version_id,
                    ).case_id
                )
                continue
            classification = self._themes.classify(proposal, self._named_themes)
            with self._db:
                self._db.execute(
                    "INSERT OR IGNORE INTO theme_classifications VALUES (?, ?, ?)",
                    (classification.classification_id, proposal.proposal_id, json.dumps(record_dict(classification), sort_keys=True)),
                )
            if not classification.resolved:
                case = self._review.open_case(
                    ReviewRequest(
                        f"request-{uuid.uuid4().hex}",
                        f"themes-{proposal.proposal_id}-{classification.classification_id}",
                        "theme_classification",
                        proposal.proposal_id,
                        {
                            "question": proposal.text,
                            "level": proposal.level.value,
                            "proposed_memberships": classification.memberships,
                            "reason_codes": classification.uncertainties,
                            "named_themes": self._named_themes,
                            "proposal": record_dict(proposal),
                            "evidence": record_dict(evaluation.evidence),
                            "outcome": record_dict(evaluation.outcome),
                            "taxonomy_version_id": enrichment_brief.taxonomy_version_id,
                            "snapshot_id": enrichment_brief.snapshot_id,
                        },
                    )
                )
                reviews.append(case.case_id)
                continue
            revision = self._bank.admit(
                AcceptedQuestionPackage(
                    f"admit-{proposal.proposal_id}-{evaluation.outcome.outcome_id}-{classification.classification_id}",
                    proposal,
                    evaluation.evidence,
                    evaluation.outcome,
                    classification,
                    enrichment_brief.taxonomy_version_id,
                    named_theme_ids=self._named_themes,
                )
            )
            accepted.append(revision.revision_id)
        result = EnrichmentRunResult(
            run_id,
            enrichment_brief.brief_id,
            tuple(proposal.proposal_id for proposal in batch.proposals),
            tuple(accepted),
            tuple(rejected),
            tuple(reviews),
            tuple(concept.concept_id for concept in batch.diverted_taxonomy_concepts),
            "completed",
        )
        with self._db:
            self._db.execute(
                "UPDATE enrichment_runs SET result_json = ?, status = 'completed' WHERE run_id = ?",
                (json.dumps(record_dict(result), sort_keys=True), run_id),
            )
        return result

    def resolve_review(self, case_id: str, resolution: HumanResolution):
        """Append a human resolution and resume the appropriate fail-closed path."""
        case = self._review.get_case(case_id)
        if resolution.action == "edit" and not resolution.edited_text:
            raise ValueError("edited_text is required for an edit resolution")
        if case.case_type == "theme_classification" and resolution.action not in {
            "resolve_themes",
            "edit",
            "reject",
            "hold",
        }:
            raise ValueError("resolution action does not match the theme review case")
        if case.case_type == "admission" and resolution.action not in {
            "accept",
            "edit",
            "reject",
            "hold",
        }:
            raise ValueError("resolution action does not match the admission review case")
        if resolution.action == "accept" and "evidence" not in case.packet:
            raise ValueError("a failed stage without evidence can only be edited, rejected, or held")
        if resolution.action == "resolve_themes":
            memberships = set(resolution.memberships or [])
            if "random" in {membership.lower() for membership in memberships}:
                raise ValueError("Random is not a stored Theme Membership")
            if not memberships.issubset(set(self._named_themes)):
                raise ValueError("human resolution contains an unknown Named Theme")
        resolution_result = self._review.resolve(case_id, resolution)
        response = {"resolution": record_dict(resolution_result), "status": "resolved"}
        if resolution.action in {"reject", "hold"}:
            return response
        packet = case.packet
        if resolution.action == "edit":
            assert resolution.edited_text is not None
            proposal = self._proposal_from_dict(packet["proposal"])
            edited = QuestionProposal(
                proposal_id=f"proposal-edit-{_stable_hash([proposal.proposal_id, resolution.edited_text])[:20]}",
                version=proposal.version + 1,
                idempotency_key=f"proposal-edit-key-{case_id}-{resolution.idempotency_key}",
                text=resolution.edited_text.strip(),
                level=proposal.level,
                aspect_id=proposal.aspect_id,
                perspective_id=proposal.perspective_id,
                semantic_scenario=proposal.semantic_scenario,
                answer_space=proposal.answer_space,
                wording_pattern=proposal.wording_pattern,
                source_permission=proposal.source_permission,
                provenance={**proposal.provenance, "edited_from": proposal.proposal_id, "human_resolution_id": resolution_result.resolution_id},
            )
            self._persist_proposal(f"human-edit-{case_id}", edited)
            evaluation = self._evaluation.evaluate(
                edited,
                {
                    "snapshot_id": packet["snapshot_id"],
                    "taxonomy_version_id": packet["taxonomy_version_id"],
                    "taxonomy_definitions": self._taxonomy_context_provider(
                        packet["taxonomy_version_id"]
                    ),
                },
            )
            self._persist_evaluation(evaluation)
            if evaluation.outcome.decision != AdmissionDecision.ACCEPT:
                if evaluation.outcome.decision == AdmissionDecision.HUMAN_REVIEW:
                    followup = self._open_admission_review(
                        edited,
                        evaluation,
                        packet["snapshot_id"],
                        packet["taxonomy_version_id"],
                    )
                    response["followup_review_case_id"] = followup.case_id
                response["status"] = evaluation.outcome.decision.value
                return response
            return self._finish_accepted_review(
                edited,
                evaluation.evidence,
                evaluation.outcome,
                packet["taxonomy_version_id"],
                packet["snapshot_id"],
                response,
            )
        proposal = self._proposal_from_dict(packet["proposal"])
        evidence = self._evidence_from_dict(packet["evidence"])
        outcome = self._outcome_from_dict(packet["outcome"])
        if case.case_type == "theme_classification" and resolution.action == "resolve_themes":
            classification = ThemeClassification(
                f"human-themes-{resolution_result.resolution_id}",
                proposal.proposal_id,
                sorted(set(resolution.memberships or [])),
                True,
                [],
                [],
            )
            revision = self._bank.admit(
                AcceptedQuestionPackage(
                    f"human-theme-admit-{resolution_result.resolution_id}",
                    proposal,
                    evidence,
                    outcome,
                    classification,
                    packet["taxonomy_version_id"],
                    named_theme_ids=self._named_themes,
                )
            )
            response.update({"status": "admitted", "revision_id": revision.revision_id})
            return response
        if case.case_type == "admission" and resolution.action == "accept":
            human_outcome = AdmissionOutcome(
                f"human-outcome-{resolution_result.resolution_id}",
                proposal.proposal_id,
                AdmissionDecision.ACCEPT,
                "human",
                evidence.evidence_id,
                resolution.reason_codes,
                outcome.outcome_id,
            )
            return self._finish_accepted_review(
                proposal,
                evidence,
                human_outcome,
                packet["taxonomy_version_id"],
                packet["snapshot_id"],
                response,
            )
        raise ValueError("resolution action does not match the review case type")

    def pending_taxonomy_support(self, limit: int = 6):
        rows = self._db.execute(
            """SELECT q.payload_json FROM taxonomy_concept_queue q
               LEFT JOIN taxonomy_concept_consumptions c ON c.concept_id = q.concept_id
               WHERE c.concept_id IS NULL ORDER BY q.rowid LIMIT ?""",
            (limit,),
        ).fetchall()
        return [CreativeConcept(**json.loads(row[0])) for row in rows]

    def mark_taxonomy_support_consumed(self, concept_ids, candidate_id: str) -> None:
        with self._db:
            for concept_id in concept_ids:
                self._db.execute(
                    "INSERT OR IGNORE INTO taxonomy_concept_consumptions VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (concept_id, candidate_id),
                )

    def rejection_reason_counts(self, run_id: str):
        rows = self._db.execute(
            """SELECT a.payload_json FROM admission_outcomes a
               JOIN proposals p ON p.proposal_id = a.proposal_id
               WHERE p.run_id = ? AND json_extract(a.payload_json, '$.decision') = 'reject'""",
            (run_id,),
        ).fetchall()
        counts: Dict[str, int] = {}
        for row in rows:
            for reason in json.loads(row[0]).get("reason_codes", []):
                counts[reason] = counts.get(reason, 0) + 1
        return counts

    def _finish_accepted_review(
        self,
        proposal,
        evidence,
        outcome,
        taxonomy_version_id,
        snapshot_id,
        response,
    ):
        classification = self._themes.classify(proposal, self._named_themes)
        if not classification.resolved:
            case = self._review.open_case(
                ReviewRequest(
                    f"request-{uuid.uuid4().hex}",
                    f"human-themes-{proposal.proposal_id}-{classification.classification_id}",
                    "theme_classification",
                    proposal.proposal_id,
                    {
                        "question": proposal.text,
                        "proposed_memberships": classification.memberships,
                        "reason_codes": classification.uncertainties,
                        "named_themes": self._named_themes,
                        "proposal": record_dict(proposal),
                        "evidence": record_dict(evidence),
                        "outcome": record_dict(outcome),
                        "taxonomy_version_id": taxonomy_version_id,
                        "snapshot_id": snapshot_id,
                    },
                )
            )
            response.update({"status": "theme_review", "followup_review_case_id": case.case_id})
            return response
        revision = self._bank.admit(
            AcceptedQuestionPackage(
                f"human-admit-{proposal.proposal_id}-{outcome.outcome_id}-{classification.classification_id}",
                proposal,
                evidence,
                outcome,
                classification,
                taxonomy_version_id,
                named_theme_ids=self._named_themes,
            )
        )
        response.update({"status": "admitted", "revision_id": revision.revision_id})
        return response

    def _persist_proposal(self, run_id, proposal) -> None:
        payload = record_dict(proposal)
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO proposals VALUES (?, ?, ?, ?)",
                (proposal.proposal_id, run_id, json.dumps(payload, sort_keys=True), json.dumps(proposal.provenance, sort_keys=True)),
            )

    def _persist_evaluation(self, evaluation) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO evaluation_evidence VALUES (?, ?, ?)",
                (evaluation.evidence.evidence_id, evaluation.evidence.proposal_id, json.dumps(record_dict(evaluation.evidence), sort_keys=True)),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO admission_outcomes VALUES (?, ?, ?)",
                (evaluation.outcome.outcome_id, evaluation.outcome.proposal_id, json.dumps(record_dict(evaluation.outcome), sort_keys=True)),
            )

    def _open_admission_review(
        self,
        proposal,
        evaluation,
        snapshot_id=None,
        taxonomy_version_id=None,
    ):
        return self._review.open_case(
            ReviewRequest(
                f"request-{uuid.uuid4().hex}",
                f"admission-{proposal.proposal_id}-{evaluation.outcome.outcome_id}",
                "admission",
                proposal.proposal_id,
                {
                    "question": proposal.text,
                    "classifications": {
                        "level": proposal.level.value,
                        "aspect_id": proposal.aspect_id,
                        "perspective_id": proposal.perspective_id,
                        "scenario": proposal.semantic_scenario,
                        "answer_space": proposal.answer_space,
                    },
                    "provenance": proposal.provenance,
                    "reason_codes": evaluation.outcome.reason_codes,
                    "evidence_id": evaluation.evidence.evidence_id,
                    "proposal": record_dict(proposal),
                    "evidence": record_dict(evaluation.evidence),
                    "outcome": record_dict(evaluation.outcome),
                    "snapshot_id": snapshot_id,
                    "taxonomy_version_id": taxonomy_version_id,
                },
            )
        )

    @staticmethod
    def _proposal_from_dict(raw):
        return QuestionProposal(**{**raw, "level": QuestionLevel(raw["level"])})

    @staticmethod
    def _evidence_from_dict(raw):
        return EvaluationEvidence(**raw)

    @staticmethod
    def _outcome_from_dict(raw):
        return AdmissionOutcome(**{**raw, "decision": AdmissionDecision(raw["decision"])})

    @staticmethod
    def _result(raw):
        return EnrichmentRunResult(
            raw["run_id"], raw["brief_id"], tuple(raw["proposal_ids"]), tuple(raw["accepted_revision_ids"]),
            tuple(raw["rejected_proposal_ids"]), tuple(raw["review_case_ids"]), tuple(raw["taxonomy_concept_ids"]), raw["status"],
        )
