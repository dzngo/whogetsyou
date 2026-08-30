"""Budgeted autonomous operating loop driven by coverage, not human gap picking."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from question_bank.agents import TaxonomyAgentGroup
from question_bank.contracts import (
    DEFAULT_POLICY_VERSIONS,
    AdmissionDecision,
    EnrichmentBrief,
    QuestionLevel,
    ReleaseIntent,
    ReviewRequest,
    record_dict,
)
from question_bank.core import QuestionBank
from question_bank.modules import (
    CompletionChallenge,
    CoveragePlanner,
    HumanReview,
    ReleaseModule,
    TaxonomyRegistry,
)
from question_bank.orchestrator import PipelineOrchestrator


class AutonomousEnrichmentLoop:
    """Selects gaps, refreshes fixed snapshots, and stops at explicit safety budgets."""

    def __init__(
        self,
        taxonomy: TaxonomyRegistry,
        coverage: CoveragePlanner,
        bank: QuestionBank,
        orchestrator: PipelineOrchestrator,
        review: HumanReview,
        release: ReleaseModule,
        completion: CompletionChallenge | None = None,
        taxonomy_agents: TaxonomyAgentGroup | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._coverage = coverage
        self._bank = bank
        self._orchestrator = orchestrator
        self._review = review
        self._release = release
        self._completion = completion or CompletionChallenge()
        self._taxonomy_agents = taxonomy_agents

    def run(
        self,
        *,
        max_iterations: int,
        concepts_per_scout: int,
        max_proposals: int,
        max_open_reviews: int,
        auto_publish: bool = False,
        spot_check_passed: bool = False,
        run_completion_challenge: bool = False,
    ) -> Dict[str, Any]:
        if max_iterations < 1 or concepts_per_scout < 1:
            raise ValueError("iteration and concept budgets must be positive")
        if max_iterations * concepts_per_scout * 4 > max_proposals:
            raise ValueError("run exceeds the configured proposal budget")
        taxonomy = self._taxonomy.current_version()
        plan = self._coverage.current_plan(taxonomy.version_id)
        results = []
        stopped_reason = "iteration_budget"
        for _ in range(max_iterations):
            if len(self._review.list_open()) >= max_open_reviews:
                stopped_reason = "review_budget"
                break
            working_snapshot = self._bank.snapshot({})
            report = self._coverage.measure(
                working_snapshot.snapshot_id,
                plan.plan_id,
                include_staged=True,
            )
            gaps = self._coverage.next_gaps(report)
            if not gaps:
                stopped_reason = "coverage_healthy"
                break
            brief = replace(
                gaps[0],
                snapshot_id=working_snapshot.snapshot_id,
                concepts_per_scout=concepts_per_scout,
            )
            results.append(record_dict(self._orchestrator.run_enrichment(brief)))
            taxonomy, plan = self._run_pending_taxonomy(taxonomy, plan)
        working_snapshot = self._bank.snapshot({})
        final_report = self._coverage.measure(
            working_snapshot.snapshot_id,
            plan.plan_id,
            include_staged=True,
        )
        release_result = None
        if auto_publish and not final_report.gaps and working_snapshot.revision_ids:
            candidate = self._release.build_candidate(
                ReleaseIntent(
                    f"auto-release-{working_snapshot.content_hash}",
                    list(working_snapshot.revision_ids),
                    taxonomy.version_id,
                    plan.plan_id,
                    dict(DEFAULT_POLICY_VERSIONS),
                    spot_check_passed,
                )
            )
            release_report = self._release.verify(candidate.snapshot_id)
            if release_report.passed:
                release_result = record_dict(self._release.publish(candidate.snapshot_id))
        enrichment_complete = False
        completion_rounds = []
        if run_completion_challenge and not final_report.gaps:
            remaining_budget = max_proposals - len(results) * concepts_per_scout * 4
            completion_rounds = self._run_completion_challenge(
                taxonomy.version_id,
                working_snapshot.snapshot_id,
                remaining_budget,
            )
            enrichment_complete = self._completion.is_complete(True, completion_rounds)
        return {
            "runs": results,
            "stopped_reason": stopped_reason,
            "coverage_report": record_dict(final_report),
            "release": release_result,
            "completion_rounds": completion_rounds,
            "enrichment_complete": enrichment_complete,
        }

    def _run_pending_taxonomy(self, taxonomy, plan):
        if self._taxonomy_agents is None:
            return taxonomy, plan
        support = self._orchestrator.pending_taxonomy_support(6)
        if len(support) < 6:
            return taxonomy, plan
        candidate, decision = self._taxonomy_agents.evaluate_gap(
            support,
            {
                "version_id": taxonomy.version_id,
                "aspects": list(taxonomy.aspects),
                "perspectives": list(taxonomy.perspectives),
            },
            record_dict(plan),
        )
        self._orchestrator.mark_taxonomy_support_consumed(
            [concept.concept_id for concept in support],
            candidate.candidate_id,
        )
        if decision.decision == AdmissionDecision.ACCEPT:
            taxonomy = self._taxonomy.release(
                {
                    "idempotency_key": f"auto-taxonomy-release-{candidate.candidate_id}",
                    "candidate_ids": [candidate.candidate_id],
                    "base_version_id": taxonomy.version_id,
                }
            )
            # A new taxon starts with no target. Preserve existing region policy
            # under the new version until independent use justifies new regions.
            plan = self._coverage.plan(
                {"version_id": taxonomy.version_id, "regions": plan.regions}
            )
        elif decision.decision == AdmissionDecision.HUMAN_REVIEW:
            self._review.open_case(
                ReviewRequest(
                    f"taxonomy-review-{candidate.candidate_id}",
                    f"taxonomy-review-key-{candidate.candidate_id}",
                    "taxonomy",
                    candidate.candidate_id,
                    {
                        "candidate": record_dict(candidate),
                        "decision": record_dict(decision),
                        "taxonomy_version_id": taxonomy.version_id,
                    },
                )
            )
        return taxonomy, plan

    def _run_completion_challenge(
        self,
        taxonomy_version_id: str,
        snapshot_id: str,
        remaining_budget: int,
    ):
        required = 3 * 2 * 20
        if remaining_budget < required:
            raise ValueError("completion challenge needs a remaining 120-concept budget")
        rounds = []
        for round_index in range(3):
            strategies = []
            for strategy in ("thinnest_regions", "open_discovery"):
                brief = EnrichmentBrief(
                    f"completion-{snapshot_id}-{round_index}-{strategy}",
                    f"completion-key-{snapshot_id}-{round_index}-{strategy}",
                    QuestionLevel.DEEP if round_index % 2 else QuestionLevel.SHALLOW,
                    {"proposal_strategy": strategy, "completion_round": round_index + 1},
                    taxonomy_version_id,
                    self._bank.snapshot({}).snapshot_id,
                    5,
                )
                result = self._orchestrator.run_enrichment(brief)
                reason_counts = self._orchestrator.rejection_reason_counts(result.run_id)
                dominant = max(reason_counts, key=reason_counts.get) if reason_counts else "quality_failure"
                strategies.append(
                    {
                        "name": strategy,
                        "concepts": 20,
                        "accepted_distinct": len(result.accepted_revision_ids),
                        "new_valid_regions": len(result.taxonomy_concept_ids),
                        "dominant_rejection": dominant,
                    }
                )
            rounds.append({"round": round_index + 1, "strategies": strategies})
        return rounds
