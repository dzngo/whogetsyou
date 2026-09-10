"""Production backend for the explicit ADK Question Bank workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import threading
from typing import Any
import uuid

from google.adk import Event

from question_bank.adk_app.workflow import BATCH_STAGE_NAMES
from question_bank.contracts import (
    CandidateReport, CandidateState, ConfigurationManifest, Level, ProviderResult,
    RunRequest, canonical_data, money, stable_hash,
)
from question_bank.diversity import observed_diversity
from question_bank.engine import EnrichmentEngine, SEMANTIC_PAIRS_PER_CALL
from question_bank.live_export import refresh_export
from question_bank.missions import missions_from_advice, slot_level
from question_bank.providers import ProviderAdapter, ProviderFailure
from question_bank.semantic import EmbeddingAdapter, normalize_question, select_review_pairs


@dataclass
class _BatchState:
    campaign_id: str
    proposal_target: int
    level: str
    budget_usd: Decimal
    batch_index: int
    request: RunRequest
    run_id: str
    execution_token: str
    plans: dict[int, tuple[Any, Level, dict]] = field(default_factory=dict)
    creative: dict[int, tuple[CandidateReport, ...]] = field(default_factory=dict)
    creative_failures: dict[int, ProviderFailure] = field(default_factory=dict)
    evaluation: tuple[CandidateReport, ...] = ()
    quality_outcomes: dict[str, str] = field(default_factory=dict)
    passing: tuple[CandidateReport, ...] = ()
    quality_uncertain: tuple[CandidateReport, ...] = ()
    semantic_outcomes: dict[str, str] = field(default_factory=dict)
    semantic_pairs: list[dict] = field(default_factory=list)
    semantic_failure: ProviderFailure | None = None
    failed_semantic_ids: set[str] = field(default_factory=set)
    staged: tuple[CandidateReport, ...] = ()
    metadata_uncertain: tuple[CandidateReport, ...] = ()
    terminal_reason: str = ""
    post_batch_reason: str = ""
    skip_creative_slots: set[int] = field(default_factory=set)
    resumed_candidates: tuple[CandidateReport, ...] = ()


class ProductionWorkflowBackend:
    """Map every visible ADK node to one real, durable production stage."""

    def __init__(
        self, root: Path, *, provider: ProviderAdapter,
        configuration: ConfigurationManifest, embedder: EmbeddingAdapter,
        observability=None,
    ) -> None:
        self.root = root
        self.engine = EnrichmentEngine(
            root, provider=provider, configuration=configuration,
            embedder=embedder, observability=observability,
        )
        self.configuration = configuration
        self.provider = provider
        self.embedder = embedder
        self.observability = self.engine._observability
        self._states: dict[str, _BatchState] = {}
        self._lock = threading.RLock()
        self._stage_lock = threading.RLock()

    def close(self) -> None:
        self.engine.close()

    def execute(self, stage: str, node_input: Any) -> Event:
        if stage.startswith("creative_agent_") or stage in {
            "campaign_status", "campaign_cancel", "campaign_resume", "command_error"
        }:
            return self._execute_stage(stage, node_input)
        with self._stage_lock:
            return self._execute_stage(stage, node_input)

    def _execute_stage(self, stage: str, node_input: Any) -> Event:
        if stage == "command_error":
            return Event(output=self._command_error(node_input))
        campaign_id = self._campaign_id(node_input)
        method = getattr(self, f"_{stage}")
        active_state: _BatchState | None = None
        if stage in BATCH_STAGE_NAMES and stage != "campaign_initialization":
            state = self._state(node_input)
            active_state = state
            self.engine._store.renew_campaign_lease(
                campaign_id, state.execution_token
            )
            self.engine._store.update_campaign(
                campaign_id, active_stage=stage
            )
        with self.observability.stage(campaign_id, stage, node_input) as observation:
            try:
                result = method(node_input)
            except Exception as error:
                observation.failure(error)
                if stage in BATCH_STAGE_NAMES:
                    token = self._execution_token(node_input)
                    if token:
                        self.engine._store.stop_campaign_execution(
                            campaign_id, token, self._reason(error)
                        )
                    else:
                        self._stop(campaign_id, self._reason(error))
                    batch_index = (
                        active_state.batch_index if active_state else int(
                            node_input.get("batch_index", 0)
                            if isinstance(node_input, dict) else 0
                        )
                    )
                    self.observability.finish_batch(
                        campaign_id, batch_index, "stopped"
                    )
                    self.observability.finish_campaign(campaign_id, "stopped")
                raise
            observation.success(result)
        if stage == "next_batch_or_complete":
            payload = result.output if isinstance(result, Event) else result
            status = str(payload.get("status", "running"))
            batch_index = active_state.batch_index if active_state else int(
                payload.get("batch_index", 0)
            )
            self.observability.finish_batch(campaign_id, batch_index, status)
            if status in {"completed", "stopped", "cancelled"}:
                self.observability.finish_campaign(campaign_id, status)
        return result if isinstance(result, Event) else Event(output=result)

    @staticmethod
    def _campaign_id(value: Any) -> str:
        if isinstance(value, dict):
            direct = value.get("campaign_id") or value.get("campaign")
            if isinstance(direct, str):
                return direct
            for nested in value.values():
                try:
                    return ProductionWorkflowBackend._campaign_id(nested)
                except ValueError:
                    continue
        raise ValueError("workflow input does not identify a campaign")

    @staticmethod
    def _execution_token(value: Any) -> str:
        if isinstance(value, dict):
            direct = value.get("execution_token")
            if isinstance(direct, str) and direct:
                return direct
            found = {
                ProductionWorkflowBackend._execution_token(nested)
                for nested in value.values()
                if isinstance(nested, (dict, list, tuple))
            }
            found.discard("")
            if len(found) == 1:
                return found.pop()
            if len(found) > 1:
                raise ValueError("workflow input mixes execution identities")
        elif isinstance(value, (list, tuple)):
            found = {
                ProductionWorkflowBackend._execution_token(nested)
                for nested in value
                if isinstance(nested, (dict, list, tuple))
            }
            found.discard("")
            if len(found) == 1:
                return found.pop()
            if len(found) > 1:
                raise ValueError("workflow input mixes execution identities")
        return ""

    def _campaign_initialization(self, node_input: Any) -> dict:
        campaign_id = self._campaign_id(node_input)
        if node_input.get("resume"):
            status = self.engine._store.campaign_status(campaign_id)
            target = int(status["proposal_target"])
            level = str(status["level"])
            budget = money(str(status["authorized_usd"]))
            batch_index = int(status["batch_index"])
            prior_run_id = status["last_run_id"]
            execution_token = str(node_input["execution_token"])
        else:
            target = int(node_input["proposal_target"])
            level = str(node_input["level"])
            budget = money(str(node_input["budget_usd"]))
            execution_token = f"execution-{uuid.uuid4().hex}"
            created = self.engine._store.create_campaign(
                campaign_id=campaign_id, proposal_target=target, level=level,
                bank=str(node_input["bank"]), budget_usd=budget,
                configuration_id=self.configuration.manifest_id,
                execution_token=execution_token,
            )
            if not created:
                raise ValueError("campaign already exists; use status or resume")
            batch_index = 0
            prior_run_id = None
        state = self._new_batch(
            campaign_id, target, level, budget, batch_index,
            prior_run_id=str(prior_run_id) if prior_run_id else None,
            resume_existing=bool(node_input.get("resume")),
            execution_token=execution_token,
        )
        with self._lock:
            self._states[campaign_id] = state
        return self._output(state)

    def _new_batch(
        self, campaign_id: str, proposal_target: int, level: str,
        budget_usd: Decimal, batch_index: int, *, prior_run_id: str | None,
        resume_existing: bool = False,
        execution_token: str,
    ) -> _BatchState:
        levels = (
            (Level.SHALLOW, Level.DEEP)
            if level == "mixed" else (Level(level),)
        )
        comparison_ids = self._comparison_ids(campaign_id)
        prefix = f"{campaign_id}-adk-batch-{batch_index}-"
        attempt = int(self.engine._store._db.execute(
            "SELECT count(*) FROM runs WHERE substr(idempotency_key,1,?)=?",
            (len(prefix), prefix),
        ).fetchone()[0])
        campaign_attempt_limit = int(
            self.engine._store.campaign_status(campaign_id)["attempt_limit"]
        )
        request = RunRequest.production_batch(
            idempotency_key=f"{prefix}{attempt}",
            snapshot_id=self.engine.empty_snapshot_id,
            batch_index=batch_index,
            authorization_usd=budget_usd,
            attempt_limit=campaign_attempt_limit,
            uncertainty_review_limit=max(6, (proposal_target // 20) * 6),
            configuration_id=self.configuration.manifest_id,
            levels=levels,
            comparison_candidate_ids=comparison_ids,
        )
        self.engine._validate_request(request)
        if resume_existing and prior_run_id:
            self.engine._store.recover_active_reservations(prior_run_id)
        run_id, _ = self.engine._store.create_run(
            request, self.configuration.manifest_id, prior_run_id=prior_run_id
        )
        self.engine._store.update_campaign(
            campaign_id, active_stage="campaign_initialization",
            batch_index=batch_index, last_run_id=run_id,
        )
        state = _BatchState(
            campaign_id, proposal_target, level, budget_usd, batch_index,
            request, run_id, execution_token,
        )
        if resume_existing and prior_run_id:
            state.resumed_candidates = self.engine._store.candidates(prior_run_id)
            strategies = {
                role.role.removeprefix("creative_"): index
                for index, role in enumerate(self.configuration.creative_roles)
            }
            counts: dict[str, int] = {}
            for candidate in state.resumed_candidates:
                counts[candidate.strategy] = counts.get(candidate.strategy, 0) + 1
            state.skip_creative_slots = {
                strategies[strategy] for strategy, count in counts.items()
                if strategy in strategies and count >= 5
            }
            state.evaluation = tuple(
                candidate for candidate in state.resumed_candidates
                if candidate.state in {
                    CandidateState.PROPOSED,
                    CandidateState.OPERATIONALLY_UNRESOLVED,
                }
            )
            state.staged = tuple(
                candidate for candidate in state.resumed_candidates
                if candidate.state == CandidateState.STAGED
                and (
                    not candidate.metadata
                    or bool(candidate.metadata.get("uncertain_fields"))
                )
            )
        return state

    def _comparison_ids(self, campaign_id: str) -> tuple[str, ...]:
        prefix = f"{campaign_id}-adk-batch-"
        rows = self.engine._store._db.execute(
            """SELECT c.candidate_id FROM candidates c JOIN runs r ON r.run_id=c.run_id
               WHERE c.state='staged' AND substr(r.idempotency_key,1,?) != ?
               ORDER BY c.candidate_id""", (len(prefix), prefix),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _mission_planner(self, node_input: Any) -> dict:
        state = self._state(node_input)
        advice = self.engine._store.prior_diversity_advice(state.run_id)
        levels = tuple(level.value for level in state.request.levels)
        missions = missions_from_advice(advice, levels)
        prior = observed_diversity(
            self.engine._comparison_candidates(state.run_id)
            + self.engine._store.prior_staged_candidates(state.run_id)
        )
        avoid = tuple(advice["avoid_patterns"]) if advice else prior.avoid_patterns
        for index, role in enumerate(self.configuration.creative_roles):
            level = Level(slot_level(index, levels))
            payload = self.engine._creative_payload(
                role, level, batch_index=state.batch_index,
                avoid_patterns=avoid,
                mission=missions[index] if missions else None,
                bootstrap_index=(state.batch_index * 4 + index if len(levels) == 1 else None),
            )
            state.plans[index] = (role, level, payload)
            self.engine._store.add_evidence(
                run_id=state.run_id, candidate_id=None,
                evidence_type="creative_mission",
                configuration_id=self.configuration.manifest_id,
                payload={
                    "role": role.role, "agent_slot": index, "level": level.value,
                    "source": "dynamic" if missions else "bootstrap_fallback",
                    "mission_id": stable_hash([role.role, payload["strategy_mission"], payload.get("mission_guidance")]),
                    "brief": payload["strategy_mission"],
                    "guidance": payload.get("mission_guidance"),
                    "advice_hash": stable_hash(advice) if missions else None,
                },
            )
        return self._output(state, planned_slots=4)

    def _creative_agent_1(self, node_input: Any) -> dict:
        return self._creative(0, node_input)

    def _creative_agent_2(self, node_input: Any) -> dict:
        return self._creative(1, node_input)

    def _creative_agent_3(self, node_input: Any) -> dict:
        return self._creative(2, node_input)

    def _creative_agent_4(self, node_input: Any) -> dict:
        return self._creative(3, node_input)

    def _creative(self, slot: int, node_input: Any) -> dict:
        state = self._state(node_input)
        if slot in state.skip_creative_slots:
            return self._output(state, slot=slot, skipped="already_persisted")
        if self._cancelled(state):
            return self._output(state, slot=slot, skipped="cancel_requested")
        role, level, payload = state.plans[slot]
        try:
            result = self._creative_invoke(state.run_id, role, payload)
            questions = self.engine._creative_questions(result)
            candidates = tuple(
                CandidateReport(
                    candidate_id=f"candidate-{stable_hash([state.run_id, role.role, i, question])[:24]}",
                    text=question, level=level,
                    strategy=role.role.removeprefix("creative_"),
                    state=CandidateState.PROPOSED,
                )
                for i, question in enumerate(questions)
            )
            with self._lock:
                state.creative[slot] = candidates
            return self._output(state, slot=slot, proposals=len(candidates))
        except ProviderFailure as failure:
            with self._lock:
                state.creative_failures[slot] = failure
            return self._output(state, slot=slot, error=self._reason(failure))

    def _creative_invoke(self, run_id: str, role: Any, payload: dict) -> ProviderResult:
        child = EnrichmentEngine(
            self.root, provider=self.provider, configuration=self.configuration,
            embedder=self.embedder, observability=self.observability,
        )
        try:
            return child._invoke(run_id, role, payload)
        finally:
            child._store.close()

    def _creative_join_and_proposal_persistence(self, node_input: Any) -> dict:
        state = self._state(node_input)
        candidates = tuple(
            candidate for slot in range(4)
            for candidate in state.creative.get(slot, ())
        )
        inserted = self.engine._store.persist_campaign_candidates(
            state.campaign_id, state.run_id, candidates,
            execution_token=state.execution_token,
        )
        if state.creative_failures:
            failures = tuple(state.creative_failures.values())
            state.post_batch_reason = next(
                (
                    self._failure_stop_reason(state, item)
                    for item in failures
                    if item.ambiguous or item.reason == "budget_or_attempt_exhausted"
                ),
                "provider_failure",
            )
        return self._output(
            state, generated_in_batch=inserted,
            failed_creative_slots=sorted(state.creative_failures),
        )

    def _duplicate_preflight(self, node_input: Any) -> dict:
        state = self._state(node_input)
        evaluation: list[CandidateReport] = []
        seen: set[str] = set()
        candidates = (
            state.evaluation + self.engine._store.candidates(state.run_id)
            if state.resumed_candidates
            else self.engine._store.candidates(state.run_id)
        )
        for candidate in candidates:
            normalized = normalize_question(candidate.text)
            if normalized in seen:
                self.engine._store.set_candidate_outcome(
                    candidate.candidate_id, CandidateState.REJECTED,
                    ("normalized_duplicate",),
                )
                self.engine._store.add_evidence(
                    run_id=state.run_id, candidate_id=candidate.candidate_id,
                    evidence_type="preflight",
                    configuration_id=self.configuration.manifest_id,
                    payload={"result": "reject", "reason_codes": ["normalized_duplicate"]},
                )
            else:
                seen.add(normalized)
                evaluation.append(candidate)
        state.evaluation = tuple(evaluation)
        return self._output(state, evaluation_count=len(evaluation))

    def _routine_quality_review(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if self._skip_paid(state):
            return self._output(state)
        role = self.configuration.role("quality_medium")
        try:
            for batch in (state.evaluation[:10], state.evaluation[10:]):
                if self._cancelled(state) or not batch:
                    continue
                result = self.engine._invoke(
                    state.run_id, role, self.engine._quality_payload(batch)
                )
                state.quality_outcomes.update(
                    self.engine._resolve_quality_batch(state.run_id, batch, result)
                )
        except ProviderFailure as failure:
            self._fail_remaining(state, failure)
        return self._output(
            state,
            quality_counts={
                outcome: tuple(state.quality_outcomes.values()).count(outcome)
                for outcome in {"pass", "reject", "uncertain"}
            },
        )

    def _uncertainty_review(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if self._skip_paid(state):
            return self._output(state)
        uncertain = [
            candidate_id for candidate_id, outcome in state.quality_outcomes.items()
            if outcome == "uncertain"
        ]
        if len(uncertain) > state.request.uncertainty_review_limit:
            state.terminal_reason = "evaluation_drift"
            self.engine._store.set_candidate_state(
                state.run_id, CandidateState.OPERATIONALLY_UNRESOLVED,
                ("evaluation_drift",),
            )
            return self._output(state)
        by_id = {candidate.candidate_id: candidate for candidate in state.evaluation}
        candidates = tuple(by_id[candidate_id] for candidate_id in uncertain)
        if candidates and not self._cancelled(state):
            try:
                result = self.engine._invoke(
                    state.run_id, self.configuration.role("quality_high"),
                    self.engine._quality_payload(candidates),
                )
                state.quality_outcomes.update(
                    self.engine._resolve_quality_batch(state.run_id, candidates, result)
                )
            except ProviderFailure as failure:
                self._fail_remaining(state, failure)
        state.passing = tuple(
            candidate for candidate in state.evaluation
            if state.quality_outcomes.get(candidate.candidate_id) == "pass"
        )
        state.quality_uncertain = tuple(
            candidate for candidate in state.evaluation
            if state.quality_outcomes.get(candidate.candidate_id) == "uncertain"
        )
        return self._output(state, uncertain_count=len(candidates))

    def _local_semantic_scan(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if state.terminal_reason:
            return self._output(state)
        try:
            outcomes, pairs = self.engine._local_semantic_scan(
                state.run_id, state.passing
            )
            state.semantic_outcomes = outcomes
            state.semantic_pairs = select_review_pairs(pairs)
        except ProviderFailure as failure:
            state.failed_semantic_ids = {
                candidate.candidate_id for candidate in state.passing
            }
            self._fail_candidates(state, state.passing, failure)
        return self._output(state, semantic_pair_count=len(state.semantic_pairs))

    def _semantic_llm_chunks(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if self._cancelled(state):
            state.failed_semantic_ids.update(
                candidate.candidate_id for candidate in state.passing
            )
            for candidate_id in state.failed_semantic_ids:
                self.engine._store.set_candidate_outcome(
                    candidate_id, CandidateState.OPERATIONALLY_UNRESOLVED,
                    ("campaign_cancelled",),
                )
            return self._output(state)
        if self._skip_paid(state):
            return self._output(state)
        if state.terminal_reason or not state.semantic_pairs:
            return self._output(state)
        resolved: dict[str, str] = {}
        role = self.configuration.role("semantic_high")
        for offset in range(0, len(state.semantic_pairs), SEMANTIC_PAIRS_PER_CALL):
            self.engine._store.renew_campaign_lease(
                state.campaign_id, state.execution_token
            )
            if self._cancelled(state):
                state.failed_semantic_ids.update(
                    pair["candidate_id"] for pair in state.semantic_pairs[offset:]
                )
                for candidate_id in state.failed_semantic_ids:
                    self.engine._store.set_candidate_outcome(
                        candidate_id, CandidateState.OPERATIONALLY_UNRESOLVED,
                        ("campaign_cancelled",),
                    )
                break
            batch = state.semantic_pairs[offset : offset + SEMANTIC_PAIRS_PER_CALL]
            try:
                result = self.engine._invoke(
                    state.run_id, role, self.engine._semantic_payload(batch)
                )
                outcomes = self.engine._resolve_semantic_batch(
                    state.run_id, batch, result
                )
                for candidate_id, outcome in outcomes.items():
                    previous = resolved.get(candidate_id)
                    if previous == "reject" or outcome == "reject":
                        resolved[candidate_id] = "reject"
                    elif previous == "uncertain" or outcome == "uncertain":
                        resolved[candidate_id] = "uncertain"
                    else:
                        resolved[candidate_id] = "pass"
            except ProviderFailure as failure:
                state.semantic_failure = failure
                state.failed_semantic_ids = {
                    pair["candidate_id"] for pair in state.semantic_pairs[offset:]
                }
                for candidate_id in state.failed_semantic_ids:
                    self.engine._store.set_candidate_outcome(
                        candidate_id, CandidateState.OPERATIONALLY_UNRESOLVED,
                        (failure.reason,),
                    )
                break
        state.semantic_outcomes.update({
            candidate_id: outcome for candidate_id, outcome in resolved.items()
            if candidate_id not in state.failed_semantic_ids
        })
        return self._output(
            state, failed_semantic_count=len(state.failed_semantic_ids)
        )

    def _admission_decision(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if state.terminal_reason and state.failed_semantic_ids:
            return self._output(state, staged_in_batch=len(state.staged))
        staged: list[CandidateReport] = list(state.staged)
        semantic_uncertain: list[CandidateReport] = []
        for candidate in state.passing:
            if candidate.candidate_id in state.failed_semantic_ids:
                continue
            outcome = state.semantic_outcomes.get(candidate.candidate_id, "uncertain")
            if outcome == "pass":
                self.engine._store.set_candidate_outcome(
                    candidate.candidate_id, CandidateState.STAGED,
                    ("quality_and_semantic_pass",),
                )
                self.engine._store.add_evidence(
                    run_id=state.run_id, candidate_id=candidate.candidate_id,
                    evidence_type="semantic_gate",
                    configuration_id=self.configuration.manifest_id,
                    payload={"deterministic_outcome": "pass"},
                )
                staged.append(candidate)
            elif outcome == "uncertain":
                self.engine._store.set_candidate_outcome(
                    candidate.candidate_id, CandidateState.AWAITING_HUMAN_REVIEW,
                    ("semantic_uncertain",),
                )
                semantic_uncertain.append(candidate)
        self.engine._allocate_admission_reviews(
            state.run_id, tuple(semantic_uncertain), state.quality_uncertain
        )
        state.staged = tuple(staged)
        return self._output(state, staged_in_batch=len(staged))

    def _observation_agent(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if state.staged and not self._skip_paid(state):
            failure = self.engine._record_diversity_advice(state.run_id)
            if failure is not None and (
                failure.ambiguous or failure.reason == "budget_or_attempt_exhausted"
            ):
                state.terminal_reason = self._failure_stop_reason(state, failure)
        return self._output(state)

    def _metadata_agent(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if not state.staged or self._skip_paid(state):
            return self._output(state)
        payload = {
            "questions": [{
                "candidate_id": candidate.candidate_id,
                "question": candidate.text,
                "level": candidate.level.value,
            } for candidate in state.staged],
            "named_themes": list(self.configuration.named_themes),
            "aspects": list(self.configuration.aspects),
            "perspectives": list(self.configuration.perspectives),
        }
        try:
            result = self.engine._invoke(
                state.run_id, self.configuration.role("metadata_medium"), payload
            )
            state.metadata_uncertain = self.engine._resolve_metadata_batch(
                state.run_id, state.staged, result
            )
        except ProviderFailure as failure:
            state.terminal_reason = (
                "unknown_spend" if failure.ambiguous else
                "metadata_budget_exhausted" if failure.reason == "budget_or_attempt_exhausted"
                else "metadata_failed"
            )
        return self._output(
            state, metadata_uncertain=len(state.metadata_uncertain)
        )

    def _final_diversity_evidence(self, node_input: Any) -> dict:
        state = self._state(node_input)
        staged_by_id = {
            candidate.candidate_id: candidate for candidate in state.staged
        }
        staged_by_id.update({
            candidate.candidate_id: candidate
            for candidate in self.engine._store.candidates(state.run_id)
            if candidate.state == CandidateState.STAGED
        })
        staged = tuple(staged_by_id.values())
        diversity = observed_diversity(staged)
        self.engine._store.add_evidence(
            run_id=state.run_id, candidate_id=None,
            evidence_type="diversity_feedback",
            configuration_id=self.configuration.manifest_id,
            payload=canonical_data(diversity),
        )
        if state.metadata_uncertain:
            allocated = self.engine._store.campaign_uncertainty_review_count(
                state.run_id
            )
            if allocated < state.request.uncertainty_review_limit:
                candidate = state.metadata_uncertain[0]
                self.engine._store.open_review_case(
                    run_id=state.run_id, candidate_id=candidate.candidate_id,
                    review_kind="metadata_uncertainty", priority=30,
                    packet=self.engine._review_packet(
                        state.run_id, candidate, ("metadata_uncertainty",)
                    ),
                )
        return self._output(state, diversity=canonical_data(diversity))

    def _persist_and_export(self, node_input: Any) -> dict:
        state = self._state(node_input)
        if self._cancelled(state):
            self.engine._store.set_candidate_state(
                state.run_id, CandidateState.OPERATIONALLY_UNRESOLVED,
                ("campaign_cancelled",),
            )
        if state.terminal_reason or state.semantic_failure or state.post_batch_reason:
            status = "stopped"
            reason = (
                state.terminal_reason
                or self._failure_stop_reason(state, state.semantic_failure)
                or state.post_batch_reason
            )
        elif self._cancelled(state):
            status, reason = "cancelled", "cancel_requested"
        elif self.engine._store.open_review_count(state.run_id):
            status, reason = "awaiting_human_review", "uncertainty_review"
        else:
            status = "completed"
            reason = "batch_complete" if state.staged else "no_staged_questions"
        self.engine._store.set_run_state(state.run_id, status, reason)
        report = self.engine._report(state.run_id)
        self.engine._store.store_report(report)
        output = self.root / (
            f"{state.campaign_id}_generated_{state.proposal_target}_"
            f"{state.level}_questions.csv"
        )
        per_level = (
            state.proposal_target if state.level != "mixed"
            else state.proposal_target // 2
        )
        exported = refresh_export(
            self.engine._store.path, output,
            f"{state.campaign_id}-adk-batch-",
            self.configuration.manifest_id, per_level=per_level,
        )
        return self._output(
            state, run_status=report.status, stop_reason=report.stop_reason,
            candidate_counts=report.metrics.get("candidate_counts", {}),
            exported=exported, csv=str(output),
        )

    def _next_batch_or_complete(self, node_input: Any) -> Event:
        state = self._state(node_input)
        counts = self._campaign_counts(state.campaign_id)
        current = self.engine._store.campaign_status(state.campaign_id)
        generated = int(current["generated_count"])
        updates: dict[str, Any] = {
            **counts, "active_stage": "next_batch_or_complete",
            "last_run_id": state.run_id,
        }
        if self._cancelled(state):
            updates["status"] = "cancelled"
        elif state.terminal_reason or state.semantic_failure or state.post_batch_reason:
            updates["status"] = "stopped"
            updates["error_code"] = (
                state.terminal_reason
                or self._failure_stop_reason(state, state.semantic_failure)
                or state.post_batch_reason
            )
        elif generated >= state.proposal_target:
            updates["status"] = "completed"
        else:
            updates["status"] = "running"
            updates["batch_index"] = state.batch_index + 1
        self.engine._store.update_campaign(state.campaign_id, **updates)
        if updates["status"] == "running":
            next_state = self._new_batch(
                state.campaign_id, state.proposal_target, state.level,
                state.budget_usd, state.batch_index + 1,
                prior_run_id=state.run_id,
                execution_token=state.execution_token,
            )
            with self._lock:
                self._states[state.campaign_id] = next_state
            return Event(route="NEXT_BATCH", output=self._output(next_state))
        return Event(output=self._output(state, **updates))

    def _campaign_status(self, node_input: Any) -> dict:
        status = self.engine._store.campaign_status(self._campaign_id(node_input))
        run_id = status.get("last_run_id")
        if run_id:
            status["spend"] = canonical_data(
                self.engine._store.ledger_summary(str(run_id))
            )
        status.pop("execution_token", None)
        status.pop("lease_expires_at", None)
        return status

    def _campaign_cancel(self, node_input: Any) -> dict:
        campaign_id = self._campaign_id(node_input)
        self.engine._store.request_campaign_cancel(campaign_id)
        return self.engine._store.campaign_status(campaign_id)

    def _campaign_resume(self, node_input: Any) -> Event:
        campaign_id = self._campaign_id(node_input)
        budget = money(str(node_input["budget_usd"]))
        execution_token = self.engine._store.resume_campaign(
            campaign_id, budget,
            expected_configuration_id=self.configuration.manifest_id,
        )
        return Event(route="RESUME", output={
            "campaign_id": campaign_id, "resume": True,
            "execution_token": execution_token,
        })

    @staticmethod
    def _command_error(node_input: Any) -> dict:
        return (
            dict(node_input) if isinstance(node_input, dict)
            else {"error": str(node_input)}
        )

    def _state(self, node_input: Any) -> _BatchState:
        campaign_id = self._campaign_id(node_input)
        token = self._execution_token(node_input)
        with self._lock:
            try:
                state = self._states[campaign_id]
            except KeyError as error:
                raise ValueError(
                    f"campaign {campaign_id!r} has no active batch"
                ) from error
        if not token or token != state.execution_token:
            raise ValueError("workflow execution is stale or does not own the campaign")
        return state

    @staticmethod
    def _output(state: _BatchState, **extra: Any) -> dict:
        return {
            "campaign_id": state.campaign_id,
            "batch_index": state.batch_index,
            "run_id": state.run_id,
            "execution_token": state.execution_token,
            "terminal_reason": state.terminal_reason,
            **canonical_data(extra),
        }

    def _cancelled(self, state: _BatchState) -> bool:
        return bool(
            self.engine._store.campaign_status(state.campaign_id)[
                "cancel_requested"
            ]
        )

    def _skip_paid(self, state: _BatchState) -> bool:
        return bool(
            state.terminal_reason or state.post_batch_reason
            or state.semantic_failure or self._cancelled(state)
        )

    def _fail_remaining(
        self, state: _BatchState, failure: ProviderFailure
    ) -> None:
        current = tuple(
            candidate for candidate in self.engine._store.candidates(state.run_id)
            if candidate.state == CandidateState.PROPOSED
        )
        remaining_by_id = {
            candidate.candidate_id: candidate
            for candidate in (*state.evaluation, *current)
            if candidate.state in {
                CandidateState.PROPOSED,
                CandidateState.OPERATIONALLY_UNRESOLVED,
            }
        }
        remaining = tuple(remaining_by_id.values())
        self._fail_candidates(state, remaining, failure)

    def _fail_candidates(
        self, state: _BatchState, candidates: tuple[CandidateReport, ...],
        failure: ProviderFailure,
    ) -> None:
        for candidate in candidates:
            self.engine._store.set_candidate_outcome(
                candidate.candidate_id,
                CandidateState.OPERATIONALLY_UNRESOLVED,
                (failure.reason,),
            )
        state.terminal_reason = self._failure_stop_reason(state, failure)

    def _failure_stop_reason(
        self, state: _BatchState, failure: ProviderFailure | None
    ) -> str:
        if failure is None:
            return ""
        if failure.ambiguous:
            return "unknown_spend"
        if failure.reason == "budget_or_attempt_exhausted":
            row = self.engine._store.run_row(state.run_id)
            return (
                "attempt_exhausted"
                if self.engine._store.campaign_attempt_count(state.run_id)
                >= int(row["attempt_limit"])
                else "budget_exhausted"
            )
        return "provider_failure"

    def _stop(self, campaign_id: str, reason: str) -> None:
        try:
            self.engine._store.update_campaign(
                campaign_id, status="stopped", error_code=reason
            )
        except KeyError:
            pass

    @staticmethod
    def _reason(error: BaseException | None) -> str:
        if error is None:
            return ""
        return str(getattr(error, "reason", type(error).__name__))

    def _campaign_counts(self, campaign_id: str) -> dict[str, int]:
        prefix = f"{campaign_id}-adk-batch-"
        rows = self.engine._store._db.execute(
            """SELECT c.text, c.state FROM candidates c
               JOIN runs r ON r.run_id = c.run_id
               WHERE substr(r.idempotency_key, 1, ?) = ?""",
            (len(prefix), prefix),
        ).fetchall()
        unique = {normalize_question(str(row["text"])) for row in rows}
        return {
            "unique_count": len(unique),
            "staged_count": sum(
                row["state"] == CandidateState.STAGED.value for row in rows
            ),
            "review_count": sum(
                row["state"] == CandidateState.AWAITING_HUMAN_REVIEW.value
                for row in rows
            ),
            "rejected_count": sum(
                row["state"] == CandidateState.REJECTED.value for row in rows
            ),
            "unresolved_count": sum(
                row["state"] == CandidateState.OPERATIONALLY_UNRESOLVED.value
                for row in rows
            ),
        }
