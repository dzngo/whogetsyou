"""Bounded, append-only human review for exact question text."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from question_bank.contracts import CandidateState, RunReport
from question_bank.store import V2Store


class HumanReview:
    """Owns review resolution without admission-stage or provider authority."""

    def __init__(self, root: Path) -> None:
        self._store = V2Store(root)

    def close(self) -> None:
        self._store.close()

    def resolve(
        self, case_id: str, resolution: dict, *, idempotency_key: str
    ) -> dict:
        if "text" in resolution:
            raise ValueError("review cannot edit question text; submit an edit as a new proposal")
        action = resolution.get("action")
        if action not in {"accept", "reject", "pass", "fail", "hold"}:
            raise ValueError("unsupported review action")
        if action == "hold":
            return self.append_supplement(
                case_id, resolution, idempotency_key=idempotency_key
            )
        existing = self._store.review_resolution_by_key(idempotency_key)
        if existing is not None:
            return existing
        case = self._store.review_case(case_id)
        metadata_update = None
        if case["review_kind"] == "metadata_uncertainty" and action in {"accept", "pass"}:
            metadata_update = self._validated_metadata_resolution(case, resolution)
        result = self._store.resolve_review_case(
            case_id,
            idempotency_key=idempotency_key,
            resolution=resolution,
            metadata_update=metadata_update,
        )
        reasons = tuple(str(item) for item in resolution.get("reason_codes", ()))
        if action in {"reject", "fail"}:
            self._store.set_candidate_outcome(
                case["candidate_id"], CandidateState.REJECTED,
                reasons or ("human_review_failure",),
            )
            self._store.set_run_state(case["run_id"], "completed", "redesign_required")
        elif action == "accept" and case["review_kind"] in {
            "quality_uncertainty", "semantic_uncertainty"
        }:
            evidence_type = f"human_{case['review_kind'].removesuffix('_uncertainty')}_resolution"
            self._store.add_evidence(
                run_id=case["run_id"],
                candidate_id=case["candidate_id"],
                evidence_type=evidence_type,
                configuration_id=case["packet"]["configuration_id"],
                payload={
                    "deterministic_outcome": "pass",
                    "review_case_id": case_id,
                    "neighbor_ids": case["packet"].get("neighbor_ids", []),
                    "reason_codes": list(reasons),
                },
            )
            self._store.set_candidate_outcome(
                case["candidate_id"], CandidateState.STAGED, ("human_accept",)
            )
        if action != "hold" and self._store.open_review_count(case["run_id"]) == 0:
            current = self._store.run_row(case["run_id"])
            if str(current["stop_reason"]) != "redesign_required":
                self._finalize(case["run_id"])
        return result

    def _validated_metadata_resolution(
        self, case: dict, resolution: dict
    ) -> tuple[tuple[str, ...] | None, dict]:
        update = resolution.get("metadata", {})
        if not isinstance(update, dict):
            raise TypeError("metadata resolution must be an object")
        candidate = self._store.candidate(case["candidate_id"])
        configuration = self._store.configuration_data(case["packet"]["configuration_id"])
        themes = candidate.theme_memberships
        metadata = dict(candidate.metadata)
        if "themes" in update:
            raw_themes = update["themes"]
            if not isinstance(raw_themes, list) or any(
                theme not in configuration["named_themes"] or theme == "Random"
                for theme in raw_themes
            ):
                raise ValueError("metadata resolution contains an unknown Theme")
            themes = tuple(sorted(set(raw_themes)))
            metadata["themes_resolved"] = True
        for field, vocabulary_key in (
            ("aspect", "aspects"),
            ("perspective", "perspectives"),
        ):
            if field in update:
                value = update[field]
                if value is not None and value not in configuration[vocabulary_key]:
                    raise ValueError(f"metadata resolution contains an unknown {field}")
                metadata[field] = value
        for field in ("scenario", "answer_space", "wording"):
            if field in update:
                value = update[field]
                if value is not None and (
                    not isinstance(value, str) or not value.strip() or len(value) > 160
                ):
                    raise ValueError(f"metadata resolution has an invalid {field}")
                metadata[field] = value
        metadata["uncertain_fields"] = tuple(
            field
            for field, value in (
                ("themes", themes if metadata.get("themes_resolved") else None),
                ("aspect", metadata.get("aspect")),
                ("perspective", metadata.get("perspective")),
                ("scenario", metadata.get("scenario")),
                ("answer_space", metadata.get("answer_space")),
                ("wording", metadata.get("wording")),
            )
            if value is None
        )
        return themes, metadata

    def append_supplement(
        self, case_id: str, evidence: dict, *, idempotency_key: str
    ) -> dict:
        return self._store.append_review_supplement(
            case_id, idempotency_key=idempotency_key, evidence=evidence
        )

    def _finalize(self, run_id: str) -> None:
        request = self._store.request_data(run_id)
        if request.get("mode") != "pilot":
            self._store.set_run_state(run_id, "completed", "review_complete")
            return
        candidates = self._store.candidates(run_id)
        staged = [item for item in candidates if item.state == CandidateState.STAGED]
        ledger = self._store.ledger_summary(run_id)
        failures = []
        if len(staged) < 14:
            failures.append("yield")
        levels = Counter(item.level.value for item in staged)
        if levels["shallow"] < 6 or levels["deep"] < 6:
            failures.append("level_yield")
        strategies = Counter(item.strategy for item in staged)
        if strategies and min(strategies.values()) < 2:
            failures.append("strategy_yield")
        exposure = ledger.reconciled_usd + ledger.active_reserved_usd + ledger.unknown_usd
        if not staged or exposure / len(staged) > __import__("decimal").Decimal("0.01"):
            failures.append("unit_cost")
        if any(item.theme_memberships is None for item in staged):
            failures.append("themes_pending")
        fields = ("aspect", "perspective", "answer_space", "wording")
        if staged and any(
            sum(item.metadata.get(field) is not None for item in staged) / len(staged) < .90
            for field in fields
        ):
            failures.append("metadata_incomplete")
        if ledger.unknown_usd or any(
            item.state == CandidateState.OPERATIONALLY_UNRESOLVED for item in candidates
        ):
            failures.append("operational_failure")
        self._store.set_run_state(
            run_id, "completed", "redesign_required" if failures else "pilot_passed"
        )

    def run_report(self, run_id: str) -> RunReport:
        row = self._store.run_row(run_id)
        return RunReport(
            run_id=run_id,
            request_id=str(row["idempotency_key"]),
            status=str(row["status"]),
            stop_reason=str(row["stop_reason"]),
            candidates=self._store.candidates(run_id),
            attempts=self._store.attempt_count(run_id),
            cache_hits=int(row["cache_hits"]),
            ledger=self._store.ledger_summary(run_id),
            configuration_id=str(row["configuration_id"]),
            snapshot_id=str(row["snapshot_id"]),
            review_case_ids=self._store.review_case_ids(run_id),
            resumable=False,
        )
