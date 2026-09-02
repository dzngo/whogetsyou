"""Deep orchestration Module for Question Bank Enrichment v2."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from question_bank.contracts import (
    CandidateReport,
    CandidateState,
    ConfigurationManifest,
    Level,
    ProviderResult,
    ReservedInvocation,
    RoleConfiguration,
    RunReport,
    RunRequest,
    canonical_data,
    money,
    stable_hash,
)
from question_bank.diversity import observed_diversity
from question_bank.providers import ProviderAdapter, ProviderFailure
from question_bank.semantic import (
    EmbeddingAdapter,
    normalize_question,
    pair_metrics,
    route_pair,
)
from question_bank.store import V2Store

PILOT_PLAN_MAX = money("0.199875")
QUALITY_STAGE_MAX = money("0.068250")


class EnrichmentEngine:
    """Owns stage ordering, spend authority, evidence, and durable outcomes."""

    def __init__(
        self,
        root: Path,
        *,
        provider: ProviderAdapter,
        configuration: ConfigurationManifest,
        embedder: EmbeddingAdapter,
    ) -> None:
        self._validate_configuration(configuration)
        self._store = V2Store(root)
        self._provider = provider
        self._configuration = configuration
        self._embedder = embedder
        self._store.install_configuration(configuration)
        self.empty_snapshot_id = self._store.ensure_empty_snapshot()

    @staticmethod
    def _validate_configuration(configuration: ConfigurationManifest) -> None:
        price_keys = {(price.provider, price.model) for price in configuration.prices}
        if len(price_keys) != len(configuration.prices):
            raise ValueError("price catalog contains duplicate entries")
        for price in configuration.prices:
            try:
                valid_through = date.fromisoformat(price.valid_through)
            except ValueError as error:
                raise ValueError("price catalog has an invalid validity date") from error
            if valid_through < datetime.now(UTC).date():
                raise ValueError("price catalog is stale")
        for role in configuration.roles:
            if (role.provider, role.model) not in price_keys:
                raise ValueError(f"price catalog is missing {role.provider}/{role.model}")
        configuration.validate_content_address()

    def close(self) -> None:
        self._store.close()

    def run(self, request: RunRequest) -> RunReport:
        self._validate_request(request)
        run_id, _ = self._store.create_run(request, self._configuration.manifest_id)
        row = self._store.run_row(run_id)
        if row["report_json"]:
            return self._report(run_id)
        if not self._store.can_fit(run_id, PILOT_PLAN_MAX, attempts=9):
            self._store.set_run_state(run_id, "stopped", "budget_exhausted")
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        batches: list[tuple[CandidateReport, ...]] = []
        prior_diversity = observed_diversity(
            self._store.prior_staged_candidates(run_id)
        )
        creative_failure: ProviderFailure | None = None
        for role_index, role in enumerate(self._configuration.creative_roles):
            level = Level.SHALLOW if role_index < 2 else Level.DEEP
            payload = self._creative_payload(
                role,
                level,
                batch_index=request.batch_index,
                avoid_patterns=prior_diversity.avoid_patterns,
            )
            try:
                result = self._invoke(run_id, role, payload)
                questions = self._creative_questions(result)
            except ProviderFailure as failure:
                creative_failure = failure
                if failure.ambiguous:
                    break
                continue
            batches.append(
                tuple(
                    CandidateReport(
                        candidate_id=f"candidate-{stable_hash([run_id, role.role, index, question])[:24]}",
                        text=question,
                        level=level,
                        strategy=role.role.removeprefix("creative_"),
                        state=CandidateState.PROPOSED,
                    )
                    for index, question in enumerate(questions)
                )
            )
        interleaved = tuple(
            candidate
            for question_index in range(5)
            for batch in batches
            for candidate in (batch[question_index],)
        )
        self._store.add_candidates(run_id, interleaved)
        if creative_failure is not None:
            self._store.set_candidate_state(
                run_id,
                CandidateState.OPERATIONALLY_UNRESOLVED,
                (creative_failure.reason,),
            )
            self._store.set_run_state(
                run_id,
                "stopped",
                "unknown_spend" if creative_failure.ambiguous else "provider_failure",
            )
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        evaluation_candidates = []
        seen_normalized: set[str] = set()
        for candidate in interleaved:
            normalized = normalize_question(candidate.text)
            if normalized in seen_normalized:
                self._store.set_candidate_outcome(
                    candidate.candidate_id,
                    CandidateState.REJECTED,
                    ("normalized_duplicate",),
                )
                self._store.add_evidence(
                    run_id=run_id,
                    candidate_id=candidate.candidate_id,
                    evidence_type="preflight",
                    configuration_id=self._configuration.manifest_id,
                    payload={"result": "reject", "reason_codes": ["normalized_duplicate"]},
                )
                continue
            seen_normalized.add(normalized)
            evaluation_candidates.append(candidate)
        evaluation_batch = tuple(evaluation_candidates)
        if not self._store.can_fit(run_id, QUALITY_STAGE_MAX, attempts=3):
            reason = (
                "attempt_exhausted"
                if self._store.attempt_count(run_id) + 3 > int(self._store.run_row(run_id)["attempt_limit"])
                else "budget_exhausted"
            )
            self._store.set_candidate_state(
                run_id, CandidateState.OPERATIONALLY_UNRESOLVED, (reason,)
            )
            self._store.set_run_state(run_id, "stopped", reason)
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        quality_role = self._configuration.role("quality_medium")
        quality_outcomes: dict[str, str] = {}
        try:
            for batch in (evaluation_batch[:10], evaluation_batch[10:]):
                if not batch:
                    continue
                result = self._invoke(
                    run_id,
                    quality_role,
                    self._quality_payload(batch),
                )
                quality_outcomes.update(self._resolve_quality_batch(run_id, batch, result))
        except ProviderFailure as failure:
            self._store.set_candidate_state(
                run_id,
                CandidateState.OPERATIONALLY_UNRESOLVED,
                (failure.reason,),
            )
            self._store.set_run_state(
                run_id,
                "stopped",
                "unknown_spend" if failure.ambiguous else "provider_failure",
            )
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        uncertain = [candidate_id for candidate_id, outcome in quality_outcomes.items() if outcome == "uncertain"]
        if uncertain:
            if len(uncertain) > 6:
                self._store.set_candidate_state(
                    run_id,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                    ("evaluation_drift",),
                )
                self._store.set_run_state(run_id, "stopped", "evaluation_drift")
                report = self._report(run_id)
                self._store.store_report(report)
                return report
            by_id = {candidate.candidate_id: candidate for candidate in evaluation_batch}
            uncertain_candidates = tuple(by_id[candidate_id] for candidate_id in uncertain)
            high_role = self._configuration.role("quality_high")
            try:
                high_result = self._invoke(
                    run_id,
                    high_role,
                    self._quality_payload(uncertain_candidates),
                )
                high_outcomes = self._resolve_quality_batch(
                    run_id, uncertain_candidates, high_result
                )
                quality_outcomes.update(high_outcomes)
            except ProviderFailure as failure:
                self._store.set_candidate_state(
                    run_id,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                    (failure.reason,),
                )
                self._store.set_run_state(
                    run_id,
                    "stopped",
                    "unknown_spend" if failure.ambiguous else "provider_failure",
                )
                report = self._report(run_id)
                self._store.store_report(report)
                return report
        passing = tuple(
            candidate
            for candidate in evaluation_batch
            if quality_outcomes.get(candidate.candidate_id) == "pass"
        )
        quality_uncertain = tuple(
            candidate
            for candidate in evaluation_batch
            if quality_outcomes.get(candidate.candidate_id) == "uncertain"
        )
        try:
            semantic_pass, semantic_pairs = self._local_semantic_scan(run_id, passing)
        except ProviderFailure as failure:
            for candidate in passing:
                self._store.set_candidate_outcome(
                    candidate.candidate_id,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                    (failure.reason,),
                )
            self._store.set_run_state(run_id, "stopped", failure.reason)
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        if len(semantic_pairs) > 12:
            affected = {pair["candidate_id"] for pair in semantic_pairs}
            for candidate_id in affected:
                self._store.set_candidate_outcome(
                    candidate_id,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                    ("pair_overflow",),
                )
            self._store.set_run_state(run_id, "stopped", "pair_overflow")
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        if semantic_pairs:
            semantic_role = self._configuration.role("semantic_high")
            try:
                semantic_result = self._invoke(
                    run_id,
                    semantic_role,
                    {"pairs": semantic_pairs},
                )
                semantic_pass.update(
                    self._resolve_semantic_batch(run_id, semantic_pairs, semantic_result)
                )
            except ProviderFailure as failure:
                self._store.set_candidate_state(
                    run_id,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                    (failure.reason,),
                )
                self._store.set_run_state(
                    run_id,
                    "stopped",
                    "unknown_spend" if failure.ambiguous else "provider_failure",
                )
                report = self._report(run_id)
                self._store.store_report(report)
                return report
        staged = []
        semantic_uncertain: list[CandidateReport] = []
        for candidate in passing:
            outcome = semantic_pass.get(candidate.candidate_id, "uncertain")
            if outcome == "pass":
                self._store.set_candidate_outcome(
                    candidate.candidate_id, CandidateState.STAGED, ("quality_and_semantic_pass",)
                )
                self._store.add_evidence(
                    run_id=run_id,
                    candidate_id=candidate.candidate_id,
                    evidence_type="semantic_gate",
                    configuration_id=self._configuration.manifest_id,
                    payload={"deterministic_outcome": "pass"},
                )
                staged.append(candidate)
            elif outcome == "uncertain":
                self._store.set_candidate_outcome(
                    candidate.candidate_id,
                    CandidateState.AWAITING_HUMAN_REVIEW,
                    ("semantic_uncertain",),
                )
                semantic_uncertain.append(candidate)
        self._allocate_admission_reviews(
            run_id, tuple(semantic_uncertain), quality_uncertain
        )
        if not staged:
            if self._store.review_count(run_id):
                self._store.set_run_state(run_id, "awaiting_human_review", "admission_review")
            else:
                self._store.set_run_state(run_id, "completed", "no_staged_questions")
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        metadata_role = self._configuration.role("metadata_medium")
        try:
            metadata_result = self._invoke(
                run_id,
                metadata_role,
                {
                    "questions": [
                        {
                            "candidate_id": candidate.candidate_id,
                            "question": candidate.text,
                            "level": candidate.level.value,
                        }
                        for candidate in staged
                    ],
                    "named_themes": list(self._configuration.named_themes),
                    "aspects": list(self._configuration.aspects),
                    "perspectives": list(self._configuration.perspectives),
                },
            )
        except ProviderFailure as failure:
            self._store.set_run_state(
                run_id,
                "stopped",
                (
                    "unknown_spend"
                    if failure.ambiguous
                    else "metadata_budget_exhausted"
                    if failure.reason == "budget_or_attempt_exhausted"
                    else "metadata_failed"
                ),
            )
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        try:
            metadata_uncertain = self._resolve_metadata_batch(
                run_id, tuple(staged), metadata_result
            )
        except ProviderFailure:
            self._store.set_run_state(run_id, "stopped", "metadata_failed")
            report = self._report(run_id)
            self._store.store_report(report)
            return report
        diversity = observed_diversity(
            tuple(
                candidate
                for candidate in self._store.candidates(run_id)
                if candidate.state == CandidateState.STAGED
            )
        )
        self._store.add_evidence(
            run_id=run_id,
            candidate_id=None,
            evidence_type="diversity_feedback",
            configuration_id=self._configuration.manifest_id,
            payload=canonical_data(diversity),
        )

        request_data = self._store.request_data(run_id)
        uncertainty_limit = int(request_data["uncertainty_review_limit"])
        allocated = self._store.campaign_uncertainty_review_count(run_id)
        if metadata_uncertain and allocated < uncertainty_limit:
            candidate = metadata_uncertain[0]
            self._store.open_review_case(
                run_id=run_id,
                candidate_id=candidate.candidate_id,
                review_kind="metadata_uncertainty",
                priority=30,
                packet=self._review_packet(run_id, candidate, ("metadata_uncertainty",)),
            )

        if request_data["mode"] == "pilot":
            protected_count = int(request_data["protected_spot_check_count"])
            selected = self._select_spot_checks(run_id, tuple(staged), protected_count)
            for index, candidate in enumerate(selected):
                self._store.open_review_case(
                    run_id=run_id,
                    candidate_id=candidate.candidate_id,
                    review_kind="protected_spot_check",
                    priority=100 + index,
                    packet=self._review_packet(
                        run_id, candidate, ("quality_and_semantic_spot_check",)
                    ),
                )
            self._store.set_run_state(run_id, "awaiting_human_review", "pilot_spot_check")
        elif self._store.open_review_count(run_id):
            self._store.set_run_state(run_id, "awaiting_human_review", "uncertainty_review")
        else:
            self._store.set_run_state(run_id, "completed", "batch_complete")
        report = self._report(run_id)
        self._store.store_report(report)
        return report

    def _allocate_admission_reviews(
        self,
        run_id: str,
        semantic_uncertain: tuple[CandidateReport, ...],
        quality_uncertain: tuple[CandidateReport, ...],
    ) -> None:
        limit = int(self._store.request_data(run_id)["uncertainty_review_limit"])
        allocated = self._store.campaign_uncertainty_review_count(run_id)
        for kind, priority, candidates in (
            ("semantic_uncertainty", 10, semantic_uncertain),
            ("quality_uncertainty", 20, quality_uncertain),
        ):
            for candidate in candidates:
                if allocated < limit:
                    self._store.set_candidate_outcome(
                        candidate.candidate_id,
                        CandidateState.AWAITING_HUMAN_REVIEW,
                        (kind,),
                    )
                    self._store.open_review_case(
                        run_id=run_id,
                        candidate_id=candidate.candidate_id,
                        review_kind=kind,
                        priority=priority,
                        packet=self._review_packet(run_id, candidate, (kind,)),
                    )
                    allocated += 1
                else:
                    self._store.set_candidate_outcome(
                        candidate.candidate_id,
                        CandidateState.REJECTED,
                        ("review_budget_exhausted",),
                    )

    def resume(self, run_id: str, new_authorization: RunRequest) -> RunReport:
        previous = self._store.run_row(run_id)
        resumable_reason = str(previous["stop_reason"]) in {
            "budget_exhausted", "unknown_spend", "provider_failure",
            "metadata_failed", "metadata_budget_exhausted",
        }
        interrupted = self._store.ledger_summary(run_id).active_reserved_usd > 0
        if not resumable_reason and not interrupted:
            raise ValueError("run is not resumable")
        self._validate_request(new_authorization)
        if new_authorization.idempotency_key == str(previous["idempotency_key"]):
            raise ValueError("resumption requires a new authorization idempotency key")
        if interrupted:
            self._store.recover_active_reservations(run_id)
            self._store.set_run_state(run_id, "stopped", "unknown_spend")
        _child_run_id, _ = self._store.create_run(
            new_authorization, self._configuration.manifest_id, prior_run_id=run_id
        )
        return self.run(new_authorization)

    def continue_campaign(self, prior_run_id: str, request: RunRequest) -> RunReport:
        prior = self._store.run_row(prior_run_id)
        if request.mode.value != "production":
            raise ValueError("campaign continuation requires production mode")
        if self._store.request_data(prior_run_id)["mode"] != "production":
            raise ValueError("prior run is not a production batch")
        if request.snapshot_id != str(prior["snapshot_id"]):
            raise ValueError("campaign continuation must keep the fixed input snapshot")
        self._validate_request(request)
        self._store.create_run(
            request, self._configuration.manifest_id, prior_run_id=prior_run_id
        )
        return self.run(request)

    def _validate_request(self, request: RunRequest) -> None:
        if request.configuration_id and request.configuration_id != self._configuration.manifest_id:
            raise ValueError("request configuration does not match engine configuration")
        if self._store.snapshot_status(request.snapshot_id) not in {"trusted", "released"}:
            raise ValueError("input snapshot must be trusted or released")
        if request.authorization_usd <= Decimal(0):
            raise ValueError("authorization must be positive")
        if request.candidate_target != 20 or request.attempt_limit < 1:
            raise ValueError("each enrichment batch must request exactly twenty candidates")
        if request.batch_index < 0:
            raise ValueError("batch index cannot be negative")

    def _report(self, run_id: str) -> RunReport:
        row = self._store.run_row(run_id)
        candidates = self._store.candidates(run_id)
        staged = tuple(item for item in candidates if item.state == CandidateState.STAGED)
        ledger = self._store.ledger_summary(run_id)
        exposure = ledger.reconciled_usd + ledger.active_reserved_usd + ledger.unknown_usd
        metadata_fields = ("aspect", "perspective", "answer_space", "wording")
        metrics = {
            "candidate_counts": {
                state.value: sum(item.state == state for item in candidates)
                for state in CandidateState
            },
            "staged_by_level": {
                level.value: sum(item.level == level for item in staged) for level in Level
            },
            "staged_by_strategy": {
                strategy: sum(item.strategy == strategy for item in staged)
                for strategy in sorted({item.strategy for item in staged})
            },
            "exposure_per_staged_usd": (
                format(money(exposure / len(staged)), "f") if staged else None
            ),
            "pessimistic_200_projection_usd": (
                format(money(exposure / len(staged) * 200), "f") if staged else None
            ),
            "metadata_resolution": {
                field: (
                    sum(item.metadata.get(field) is not None for item in staged) / len(staged)
                    if staged else 0.0
                )
                for field in metadata_fields
            },
        }
        return RunReport(
            run_id=run_id,
            request_id=str(row["idempotency_key"]),
            status=str(row["status"]),
            stop_reason=str(row["stop_reason"]),
            candidates=candidates,
            attempts=self._store.attempt_count(run_id),
            cache_hits=int(row["cache_hits"]),
            ledger=ledger,
            configuration_id=str(row["configuration_id"]),
            snapshot_id=str(row["snapshot_id"]),
            review_case_ids=self._store.review_case_ids(run_id),
            resumable=str(row["stop_reason"]) in {
                "budget_exhausted",
                "unknown_spend",
                "provider_failure",
                "metadata_failed",
                "metadata_budget_exhausted",
            },
            metrics=metrics,
        )

    def _resolve_metadata_batch(
        self,
        run_id: str,
        candidates: tuple[CandidateReport, ...],
        result: ProviderResult,
    ) -> tuple[CandidateReport, ...]:
        records = result.output.get("records")
        if not isinstance(records, list):
            raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
        expected = {candidate.candidate_id: candidate for candidate in candidates}
        indexed: dict[str, dict] = {}
        for raw in records:
            if not isinstance(raw, dict) or not isinstance(raw.get("candidate_id"), str):
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            candidate_id = raw["candidate_id"]
            if candidate_id not in expected or candidate_id in indexed:
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            indexed[candidate_id] = raw
        if set(indexed) != set(expected):
            raise ProviderFailure("malformed_metadata_batch", ambiguous=False)

        uncertain: list[CandidateReport] = []
        prepared: list[tuple[str, dict, tuple[str, ...] | None, dict]] = []
        allowed_fields = {"themes", "aspect", "perspective", "scenario", "answer_space", "wording"}
        for candidate_id, record in indexed.items():
            raw_themes = record.get("themes")
            themes_resolved = record.get("themes_resolved")
            if not isinstance(themes_resolved, bool):
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            if themes_resolved:
                if not isinstance(raw_themes, list) or any(
                    not isinstance(theme, str)
                    or theme == "Random"
                    or theme not in self._configuration.named_themes
                    for theme in raw_themes
                ):
                    raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
                themes: tuple[str, ...] | None = tuple(sorted(set(raw_themes)))
            else:
                if raw_themes not in (None, []):
                    raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
                themes = None
            aspect = record.get("aspect")
            perspective = record.get("perspective")
            if aspect is not None and aspect not in self._configuration.aspects:
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            if perspective is not None and perspective not in self._configuration.perspectives:
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            for field in ("scenario", "answer_space", "wording"):
                value = record.get(field)
                if value is not None and (
                    not isinstance(value, str) or not value.strip() or len(value) > 160
                ):
                    raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            uncertain_fields = record.get("uncertain_fields")
            if not isinstance(uncertain_fields, list) or any(
                field not in allowed_fields for field in uncertain_fields
            ):
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            inferred_pending = {
                field
                for field, value in {
                    "themes": themes if themes_resolved else None,
                    "aspect": aspect,
                    "perspective": perspective,
                    "scenario": record.get("scenario"),
                    "answer_space": record.get("answer_space"),
                    "wording": record.get("wording"),
                }.items()
                if value is None
            }
            if set(uncertain_fields) != inferred_pending:
                raise ProviderFailure("malformed_metadata_batch", ambiguous=False)
            metadata = {
                "themes_resolved": themes_resolved,
                "aspect": aspect,
                "perspective": perspective,
                "scenario": record.get("scenario"),
                "answer_space": record.get("answer_space"),
                "wording": record.get("wording"),
                "uncertain_fields": tuple(sorted(uncertain_fields)),
            }
            prepared.append((candidate_id, record, themes, metadata))
            if uncertain_fields:
                uncertain.append(expected[candidate_id])
        for candidate_id, record, themes, metadata in prepared:
            self._store.set_candidate_metadata(
                candidate_id, themes=themes, metadata=metadata
            )
            self._store.add_evidence(
                run_id=run_id,
                candidate_id=candidate_id,
                evidence_type="metadata",
                configuration_id=self._configuration.manifest_id,
                payload={**record, "validated": True},
            )
        return tuple(uncertain)

    def _review_packet(
        self, run_id: str, candidate: CandidateReport, reason_codes: tuple[str, ...]
    ) -> dict:
        evidence = self._store.candidate_evidence_summary(run_id, candidate.candidate_id)
        return {
            "candidate_id": candidate.candidate_id,
            "text": candidate.text,
            "level": candidate.level.value,
            "strategy": candidate.strategy,
            "provenance": {
                "origin": "model_generated",
                "creative_strategy": candidate.strategy,
            },
            "snapshot_id": str(self._store.run_row(run_id)["snapshot_id"]),
            "configuration_id": self._configuration.manifest_id,
            "reason_codes": list(reason_codes),
            **evidence,
        }

    def _select_spot_checks(
        self, run_id: str, candidates: tuple[CandidateReport, ...], count: int
    ) -> tuple[CandidateReport, ...]:
        unavailable = set(self._store.review_candidate_ids(run_id))
        candidates = tuple(
            candidate for candidate in candidates if candidate.candidate_id not in unavailable
        )
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        selected: list[CandidateReport] = []
        for left_id, right_id in self._store.semantic_risk_candidate_pairs(run_id)[:2]:
            for candidate_id in (left_id, right_id):
                candidate = by_id.get(candidate_id)
                if candidate is not None and candidate not in selected:
                    selected.append(candidate)
                    if len(selected) == count:
                        return tuple(selected)
        # Fill missing positions with a stable spread across level and strategy.
        seen_groups: set[tuple[Level, str]] = set()
        for candidate in candidates:
            group = (candidate.level, candidate.strategy)
            if group not in seen_groups:
                selected.append(candidate)
                seen_groups.add(group)
                if len(selected) == count:
                    return tuple(selected)
        selected_ids = {item.candidate_id for item in selected}
        selected.extend(
            candidate
            for candidate in candidates
            if candidate.candidate_id not in selected_ids
        )
        return tuple(selected[:count])

    @staticmethod
    def _quality_payload(candidates: tuple[CandidateReport, ...]) -> dict:
        return {
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "question": item.text,
                    "level": item.level.value,
                }
                for item in candidates
            ],
            "rubric": [
                "clarity",
                "answerability",
                "emotional_safety",
                "level_fit",
                "deep_revelation",
            ],
            "instructions": "Judge each question independently. Do not rank or apply quotas.",
        }

    def _resolve_quality_batch(
        self,
        run_id: str,
        candidates: tuple[CandidateReport, ...],
        result: ProviderResult,
    ) -> dict[str, str]:
        records = result.output.get("records")
        if not isinstance(records, list):
            raise ProviderFailure("malformed_quality_batch", ambiguous=False)
        expected = {candidate.candidate_id: candidate for candidate in candidates}
        indexed: dict[str, dict] = {}
        for raw in records:
            if not isinstance(raw, dict) or not isinstance(raw.get("candidate_id"), str):
                raise ProviderFailure("malformed_quality_batch", ambiguous=False)
            candidate_id = raw["candidate_id"]
            if candidate_id in indexed or candidate_id not in expected:
                raise ProviderFailure("malformed_quality_batch", ambiguous=False)
            indexed[candidate_id] = raw
        if set(indexed) != set(expected):
            raise ProviderFailure("malformed_quality_batch", ambiguous=False)
        outcomes: dict[str, str] = {}
        rejection_reasons: dict[str, tuple[str, ...]] = {}
        required = (
            "clarity",
            "answerability",
            "emotional_safety",
            "level_fit",
            "deep_revelation",
        )
        for candidate_id, record in indexed.items():
            candidate = expected[candidate_id]
            values = []
            for field in required:
                value = record.get(field)
                allowed = {"pass", "fail", "uncertain"}
                if field == "deep_revelation" and candidate.level == Level.SHALLOW:
                    allowed.add("not_applicable")
                if value not in allowed:
                    raise ProviderFailure("malformed_quality_batch", ambiguous=False)
                if value != "not_applicable":
                    values.append(value)
            if "fail" in values:
                outcome = "reject"
                rejection_reasons[candidate_id] = tuple(
                    str(code)
                    for code in record.get("reason_codes", ["quality_failure"])
                )
            elif "uncertain" in values:
                outcome = "uncertain"
            else:
                outcome = "pass"
            outcomes[candidate_id] = outcome
        for candidate_id, record in indexed.items():
            outcome = outcomes[candidate_id]
            if outcome == "reject":
                self._store.set_candidate_outcome(
                    candidate_id,
                    CandidateState.REJECTED,
                    rejection_reasons[candidate_id],
                )
            self._store.add_evidence(
                run_id=run_id,
                candidate_id=candidate_id,
                evidence_type="quality",
                configuration_id=self._configuration.manifest_id,
                payload={**record, "deterministic_outcome": outcome},
            )
        return outcomes

    def _local_semantic_scan(
        self, run_id: str, candidates: tuple[CandidateReport, ...]
    ) -> tuple[dict[str, str], list[dict]]:
        if not candidates:
            return {}, []
        trusted = self._store.snapshot_questions(
            str(self._store.run_row(run_id)["snapshot_id"])
        )
        trusted = trusted + self._store.prior_staged_questions(run_id)
        all_texts = [text for _, text in trusted] + [candidate.text for candidate in candidates]
        vectors = self._embedder.embed(all_texts)
        if len(vectors) != len(all_texts):
            raise ProviderFailure("embedding_unavailable", ambiguous=False)
        outcomes: dict[str, str] = {}
        ambiguous: list[dict] = []
        trusted_vectors = vectors[: len(trusted)]
        candidate_vectors = vectors[len(trusted) :]
        kept: list[tuple[str, str, tuple[float, ...]]] = [
            (question_id, text, tuple(vector))
            for (question_id, text), vector in zip(trusted, trusted_vectors, strict=True)
        ]
        for candidate, vector in zip(candidates, candidate_vectors, strict=True):
            rejected = False
            candidate_pairs = []
            for neighbor_id, neighbor_text, neighbor_vector in kept:
                metrics = pair_metrics(candidate.text, neighbor_text, vector, neighbor_vector)
                route = route_pair(candidate.text, neighbor_text, metrics)
                evidence_payload = {
                    "candidate_id": candidate.candidate_id,
                    "neighbor_id": neighbor_id,
                    "route": route,
                    "token_jaccard": metrics.token_jaccard,
                    "token_containment": metrics.token_containment,
                    "character_cosine": metrics.character_cosine,
                    "embedding_cosine": metrics.embedding_cosine,
                }
                self._store.add_evidence(
                    run_id=run_id,
                    candidate_id=candidate.candidate_id,
                    evidence_type="local_semantic_pair",
                    configuration_id=self._configuration.manifest_id,
                    payload=evidence_payload,
                )
                if route == "local_reject":
                    self._store.set_candidate_outcome(
                        candidate.candidate_id,
                        CandidateState.REJECTED,
                        ("semantic_near_copy",),
                    )
                    outcomes[candidate.candidate_id] = "reject"
                    rejected = True
                    break
                if route == "gpt_review" or (
                    route == "local_distance"
                    and not self._configuration.local_distance_authority
                ):
                    pair_id = f"pair-{stable_hash([candidate.candidate_id, neighbor_id])[:24]}"
                    candidate_pairs.append(
                        {
                            "pair_id": pair_id,
                            "candidate_id": candidate.candidate_id,
                            "candidate_text": candidate.text,
                            "neighbor_id": neighbor_id,
                            "neighbor_text": neighbor_text,
                            **evidence_payload,
                        }
                    )
            if rejected:
                continue
            kept.append((candidate.candidate_id, candidate.text, tuple(vector)))
            if candidate_pairs:
                ambiguous.extend(candidate_pairs)
                outcomes[candidate.candidate_id] = "pending"
            else:
                outcomes[candidate.candidate_id] = "pass"
        return outcomes, ambiguous

    def _resolve_semantic_batch(
        self, run_id: str, requested_pairs: list[dict], result: ProviderResult
    ) -> dict[str, str]:
        raw_pairs = result.output.get("pairs")
        if not isinstance(raw_pairs, list):
            raise ProviderFailure("malformed_semantic_batch", ambiguous=False)
        expected = {pair["pair_id"]: pair for pair in requested_pairs}
        indexed = {}
        for raw in raw_pairs:
            if not isinstance(raw, dict) or raw.get("pair_id") not in expected:
                raise ProviderFailure("malformed_semantic_batch", ambiguous=False)
            if raw["pair_id"] in indexed:
                raise ProviderFailure("malformed_semantic_batch", ambiguous=False)
            indexed[raw["pair_id"]] = raw
        if set(indexed) != set(expected):
            raise ProviderFailure("malformed_semantic_batch", ambiguous=False)
        candidate_relations: dict[str, list[str]] = {}
        resolved_records: list[tuple[dict, dict, str]] = []
        allowed_relations = {"same", "overlapping", "different", "opposed", "uncertain"}
        for pair_id, record in indexed.items():
            values = [
                record.get("scenario"),
                record.get("perspective"),
                record.get("answer_space"),
                record.get("aspect"),
                record.get("wording"),
            ]
            if any(value not in allowed_relations for value in values):
                raise ProviderFailure("malformed_semantic_batch", ambiguous=False)
            primary = values[:3]
            derived_repeat = all(value in {"same", "overlapping"} for value in primary)
            verdict = record.get("verdict")
            if "uncertain" in values or verdict == "uncertain":
                outcome = "uncertain"
            elif verdict == "repeat" and derived_repeat:
                outcome = "repeat"
            elif verdict == "distinct" and not derived_repeat:
                outcome = "distinct"
            else:
                outcome = "uncertain"
            pair = expected[pair_id]
            candidate_relations.setdefault(pair["candidate_id"], []).append(outcome)
            resolved_records.append((pair, record, outcome))
        for pair, record, outcome in resolved_records:
            self._store.add_evidence(
                run_id=run_id,
                candidate_id=pair["candidate_id"],
                evidence_type="semantic_relation",
                configuration_id=self._configuration.manifest_id,
                payload={
                    **pair,
                    **record,
                    "deterministic_outcome": outcome,
                },
            )
        outcomes = {}
        for candidate_id, relations in candidate_relations.items():
            if "repeat" in relations:
                outcomes[candidate_id] = "reject"
                self._store.set_candidate_outcome(
                    candidate_id,
                    CandidateState.REJECTED,
                    ("semantic_repeat",),
                )
            elif "uncertain" in relations:
                outcomes[candidate_id] = "uncertain"
            else:
                outcomes[candidate_id] = "pass"
        return outcomes

    @staticmethod
    def _creative_payload(
        role: RoleConfiguration,
        level: Level,
        *,
        batch_index: int = 0,
        avoid_patterns: tuple[str, ...] = (),
    ) -> dict:
        missions = {
            "creative_concrete_life_moments": "Use concrete life moments rather than abstract self-description.",
            "creative_relational_mirrors": "Explore closeness, repair, misunderstanding, and being seen.",
            "creative_tensions_tradeoffs": "Explore choices where legitimate values pull apart.",
            "creative_inner_signals": "Explore subtle inner evidence that other people may not observe.",
        }
        return {
            "level": level.value,
            "quality_floor": {
                "clear": True,
                "answerable": True,
                "emotionally_safe": True,
                "deep_reveals_characteristic": level == Level.DEEP,
            },
            "strategy_mission": missions[role.role],
            "batch_index": batch_index,
            "bank_avoidance_summary": list(avoid_patterns[:8]),
            "output_schema": {"questions": ["question"] * 5},
        }

    @staticmethod
    def _creative_questions(result: ProviderResult) -> tuple[str, ...]:
        raw = result.output.get("questions")
        if not isinstance(raw, list) or len(raw) != 5:
            raise ProviderFailure("malformed_creative_batch", ambiguous=False)
        questions = tuple(str(question).strip() for question in raw)
        if any(not question for question in questions) or len(set(questions)) != 5:
            raise ProviderFailure("malformed_creative_batch", ambiguous=False)
        return questions

    def _invoke(
        self, run_id: str, role: RoleConfiguration, payload: dict
    ) -> ProviderResult:
        def logical_input(value):
            if isinstance(value, dict):
                return {
                    key: logical_input(item)
                    for key, item in value.items()
                    if key not in {"candidate_id", "pair_id", "neighbor_id"}
                }
            if isinstance(value, list):
                return [logical_input(item) for item in value]
            return value

        input_hash = stable_hash(
            {
                "configuration": self._configuration.manifest_id,
                "role": canonical_data(role),
                "payload": logical_input(payload),
            }
        )
        invocation_key = f"{role.role}-{input_hash}"
        if self._store.prior_unknown_invocation(
            run_id, role=role.role, input_hash=input_hash
        ):
            raise ProviderFailure("prior_unknown_invocation", ambiguous=True)
        cached = (
            self._store.cached_result(
                configuration_id=self._configuration.manifest_id,
                role=role.role,
                input_hash=input_hash,
                run_id=run_id,
            )
            if role.role.startswith("creative_")
            else None
        )
        if cached is not None:
            return cached
        reserved = self._store.reserve(
            run_id,
            invocation_key=invocation_key,
            role=role.role,
            provider=role.provider,
            model=role.model,
            reservation_usd=role.reservation_usd,
            input_hash=input_hash,
        )
        if reserved is None:
            raise ProviderFailure("budget_or_attempt_exhausted", ambiguous=False)
        reservation_id, invocation_id = reserved
        invocation = ReservedInvocation(
            run_id=run_id,
            invocation_id=invocation_id,
            idempotency_key=invocation_key,
            role=role,
            payload=payload,
            reservation_id=reservation_id,
        )
        try:
            result = self._provider.invoke(invocation)
        except ProviderFailure as failure:
            self._store.fail_invocation(
                reservation_id,
                invocation_id,
                error_code=failure.reason,
                ambiguous=failure.ambiguous,
            )
            raise
        if result.reported_model not in role.reported_model_identities:
            self._store.fail_invocation(
                reservation_id,
                invocation_id,
                error_code="unexpected_model_identity",
                ambiguous=True,
            )
            raise ProviderFailure("unexpected_model_identity", ambiguous=True)
        try:
            actual = self._actual_cost(role, result)
        except ProviderFailure as failure:
            self._store.fail_invocation(
                reservation_id,
                invocation_id,
                error_code=failure.reason,
                ambiguous=failure.ambiguous,
            )
            raise
        if actual > role.reservation_usd:
            self._store.fail_invocation(
                reservation_id,
                invocation_id,
                error_code="actual_cost_exceeded_reservation",
                ambiguous=True,
            )
            raise ProviderFailure("actual_cost_exceeded_reservation", ambiguous=True)
        self._store.reconcile(
            reservation_id,
            invocation_id,
            actual_usd=actual,
            output=dict(result.output),
            usage=canonical_data(result.usage),
            reported_model=result.reported_model,
            response_id=result.response_id,
        )
        return result

    def _actual_cost(self, role: RoleConfiguration, result: ProviderResult):
        usage = result.usage
        if min(
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
            usage.reasoning_or_thought_tokens,
            usage.total_tokens,
        ) < 0 or usage.input_tokens < usage.cached_input_tokens:
            raise ProviderFailure("invalid_provider_usage", ambiguous=False)
        if usage.input_tokens > role.input_token_limit:
            raise ProviderFailure("provider_usage_exceeded_bound", ambiguous=False)
        if role.provider == "gemini":
            generated = usage.output_tokens + usage.reasoning_or_thought_tokens
            if role.total_generated_token_limit is None or generated > role.total_generated_token_limit:
                raise ProviderFailure("provider_usage_exceeded_bound", ambiguous=False)
        elif usage.output_tokens > role.output_token_limit:
            raise ProviderFailure("provider_usage_exceeded_bound", ambiguous=False)
        price = next(
            entry
            for entry in self._configuration.prices
            if entry.provider == role.provider and entry.model == role.model
        )
        uncached = usage.input_tokens - usage.cached_input_tokens
        generated = (
            usage.output_tokens + usage.reasoning_or_thought_tokens
            if role.provider == "gemini"
            else usage.output_tokens
        )
        return money(
            Decimal(uncached) * price.uncached_input_per_million / Decimal(1_000_000)
            + Decimal(usage.cached_input_tokens)
            * price.cached_input_per_million
            / Decimal(1_000_000)
            + Decimal(generated) * price.output_per_million / Decimal(1_000_000)
        )
