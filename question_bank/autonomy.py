"""Budgeted autonomous operating loop driven by coverage, not human gap picking."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict

from question_bank.agents import CoveragePlanAgentGroup, TaxonomyAgentGroup
from question_bank.contracts import (
    DEFAULT_POLICY_VERSIONS,
    AdmissionDecision,
    EnrichmentBrief,
    QuestionLevel,
    ReleaseIntent,
    ReviewRequest,
    TaxonomyVersion,
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
        coverage_agents: CoveragePlanAgentGroup | None = None,
        theme_definitions: Dict[str, Any] | None = None,
        taxonomy_activator: Callable[[TaxonomyVersion, Any], TaxonomyVersion]
        | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._coverage = coverage
        self._bank = bank
        self._orchestrator = orchestrator
        self._review = review
        self._release = release
        self._completion = completion or CompletionChallenge()
        self._taxonomy_agents = taxonomy_agents
        self._coverage_agents = coverage_agents
        self._theme_definitions = theme_definitions or {}
        self._taxonomy_activator = taxonomy_activator

    def run(
        self,
        *,
        max_iterations: int,
        concepts_per_scout: int,
        max_proposals: int,
        max_open_reviews: int,
        auto_publish: bool = False,
        spot_check_passed: bool = False,
        spot_check_id: str | None = None,
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
            working_snapshot = self._working_snapshot()
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
                snapshot_id=self._evaluation_snapshot_id(),
                concepts_per_scout=concepts_per_scout,
            )
            run_result = self._orchestrator.run_enrichment(brief)
            if not run_result.eligible_for_completion:
                run_result = self._orchestrator.run_enrichment(brief)
            results.append(record_dict(run_result))
            if not run_result.eligible_for_completion:
                stopped_reason = "stage_failure_requeued"
                break
            taxonomy, plan = self._run_pending_taxonomy(taxonomy, plan)
        working_snapshot = self._working_snapshot()
        final_report = self._coverage.measure(
            working_snapshot.snapshot_id,
            plan.plan_id,
            include_staged=True,
        )
        enrichment_complete = False
        completion_rounds = []
        remaining_budget = max_proposals - len(results) * concepts_per_scout * 4
        if not final_report.gaps and remaining_budget >= 144:
            completion_rounds, taxonomy, plan = self._run_completion_challenge(
                taxonomy.version_id,
                working_snapshot.snapshot_id,
                remaining_budget,
                final_report,
                plan,
            )
            enrichment_complete = self._completion.is_complete(True, completion_rounds)
            # Challenge proposals enter the same trusted workflow, so bind the
            # completion decision to the resulting snapshot and fresh report.
            working_snapshot = self._working_snapshot()
            final_report = self._coverage.measure(
                working_snapshot.snapshot_id,
                plan.plan_id,
                include_staged=True,
            )
            enrichment_complete = self._completion.is_complete(
                not final_report.gaps, completion_rounds
            )
        elif not final_report.gaps and not enrichment_complete:
            stopped_reason = "completion_budget"
        completion_record_id = self._coverage.record_completion(
            working_snapshot.snapshot_id,
            taxonomy.version_id,
            plan.plan_id,
            dict(DEFAULT_POLICY_VERSIONS),
            completion_rounds,
            enrichment_complete,
        )
        completion_invalidated = any(
            strategy.get("new_valid_regions", 0)
            or strategy.get("unresolved_region_discoveries", 0)
            for round_result in completion_rounds
            for strategy in round_result.get("strategies", [])
        )
        if completion_invalidated:
            stopped_reason = "completion_discovery"
        release_result = None
        if (
            auto_publish
            and not completion_invalidated
            and not final_report.gaps
            and working_snapshot.revision_ids
        ):
            candidate = self._release.build_candidate(
                ReleaseIntent(
                    idempotency_key=f"auto-release-{working_snapshot.content_hash}",
                    revision_ids=list(working_snapshot.revision_ids),
                    taxonomy_version_id=taxonomy.version_id,
                    coverage_plan_id=plan.plan_id,
                    policy_versions=dict(DEFAULT_POLICY_VERSIONS),
                    spot_check_passed=spot_check_passed,
                    spot_check_id=spot_check_id,
                    completion_record_id=completion_record_id,
                )
            )
            release_report = self._release.verify(candidate.snapshot_id)
            if release_report.passed:
                release_result = record_dict(self._release.publish(candidate.snapshot_id))
        return {
            "runs": results,
            "stopped_reason": stopped_reason,
            "coverage_report": record_dict(final_report),
            "release": release_result,
            "completion_rounds": completion_rounds,
            "enrichment_complete": enrichment_complete,
            "completion_record_id": completion_record_id,
        }

    def _run_pending_taxonomy(self, taxonomy, plan):
        if self._taxonomy_agents is None:
            return taxonomy, plan
        support = self._orchestrator.pending_taxonomy_support(6)
        if len(support) < 6:
            return taxonomy, plan
        candidate, decision = self._taxonomy_agents.evaluate_gap(
            support,
            self._taxonomy.definition_context(taxonomy.version_id),
            record_dict(plan),
        )
        self._orchestrator.mark_taxonomy_support_consumed(
            [concept.concept_id for concept in support],
            candidate.candidate_id,
        )
        if decision.decision == AdmissionDecision.ACCEPT:
            staged_taxonomy = self._taxonomy.release(
                {
                    "idempotency_key": f"auto-taxonomy-release-{candidate.candidate_id}",
                    "candidate_ids": [candidate.candidate_id],
                    "base_version_id": taxonomy.version_id,
                },
                staged=True,
            )
            if self._coverage_agents is None or not self._theme_definitions:
                raise RuntimeError(
                    "taxonomy release requires agent-classified coverage regions"
                )
            coverage_result = self._coverage_agents.generate(
                self._taxonomy.definition_context(
                    staged_taxonomy.version_id, allow_staged=True
                ),
                self._theme_definitions,
            )
            if coverage_result["status"] == "planned":
                staged_plan = self._coverage.current_plan(staged_taxonomy.version_id)
                if self._taxonomy_activator is None:
                    raise RuntimeError(
                        "taxonomy activation requires a Reference regression gate"
                    )
                taxonomy = self._taxonomy_activator(
                    staged_taxonomy, staged_plan
                )
                plan = staged_plan
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
        coverage_report,
        coverage_plan,
    ):
        required = 3 * 2 * 24
        if remaining_budget < required:
            raise ValueError("completion challenge needs a remaining 144-concept budget")
        rounds = []
        challenge_taxonomy = self._taxonomy.version_record(taxonomy_version_id)
        challenge_plan = coverage_plan
        discovery_invalidated = False
        region_by_id = {region.region_id: region for region in coverage_plan.regions}
        thinnest_ids = sorted(
            coverage_report.region_counts,
            key=lambda region_id: (
                coverage_report.region_counts[region_id],
                coverage_report.scenario_counts.get(region_id, 0),
                region_id,
            ),
        )[:5]
        thinnest_regions = [
            record_dict(region_by_id[region_id])
            for region_id in thinnest_ids
            if region_id in region_by_id
        ]
        for round_index in range(3):
            strategies = []
            for strategy in ("structured_mix", "contrast_mix"):
                strategy_results = []
                reason_counts: Dict[str, int] = {}
                for discovery_mode in ("thinnest_regions", "open_discovery"):
                    brief = EnrichmentBrief(
                        f"completion-{snapshot_id}-{round_index}-{strategy}-{discovery_mode}",
                        f"completion-key-{snapshot_id}-{round_index}-{strategy}-{discovery_mode}",
                        QuestionLevel.DEEP if round_index % 2 else QuestionLevel.SHALLOW,
                        {
                            "proposal_strategy": strategy,
                            "completion_round": round_index + 1,
                            "discovery_mode": discovery_mode,
                            "thinnest_regions": (
                                thinnest_regions
                                if discovery_mode == "thinnest_regions"
                                else []
                            ),
                            "new_taxon_hint": None,
                        },
                        taxonomy_version_id,
                        self._evaluation_snapshot_id(),
                        3,
                    )
                    result = self._orchestrator.run_enrichment(brief)
                    strategy_results.append(result)
                    for reason, count in self._orchestrator.rejection_reason_counts(
                        result.run_id
                    ).items():
                        reason_counts[reason] = reason_counts.get(reason, 0) + count
                dominant = (
                    max(reason_counts, key=lambda reason: reason_counts[reason])
                    if reason_counts
                    else "quality_failure"
                )
                queued_support = self._orchestrator.pending_taxonomy_support(6)
                new_valid_regions = 0
                unresolved_discoveries = 0
                if len(queued_support) >= 6:
                    previous_version_id = challenge_taxonomy.version_id
                    challenge_taxonomy, challenge_plan = self._run_pending_taxonomy(
                        challenge_taxonomy, challenge_plan
                    )
                    if challenge_taxonomy.version_id != previous_version_id:
                        new_valid_regions = 1
                    else:
                        unresolved_discoveries = len(queued_support)
                    discovery_invalidated = True
                strategies.append(
                    {
                        "name": strategy,
                        "concepts": sum(result.concept_count for result in strategy_results),
                        "eligible": all(
                            result.eligible_for_completion for result in strategy_results
                        )
                        and unresolved_discoveries == 0,
                        "accepted_distinct": sum(
                            len(result.accepted_revision_ids)
                            for result in strategy_results
                        ),
                        "new_valid_regions": new_valid_regions,
                        "unresolved_region_discoveries": unresolved_discoveries,
                        "dominant_rejection": dominant,
                    }
                )
                if discovery_invalidated:
                    break
            rounds.append({"round": round_index + 1, "strategies": strategies})
            if discovery_invalidated:
                break
        return rounds, challenge_taxonomy, challenge_plan

    def _evaluation_snapshot_id(self) -> str:
        released = self._release.current_bank_snapshot_id()
        if released:
            return released
        return self._bank.snapshot({"revision_ids": []}).snapshot_id

    def _working_snapshot(self):
        return self._bank.working_snapshot(self._release.current_bank_snapshot_id())
