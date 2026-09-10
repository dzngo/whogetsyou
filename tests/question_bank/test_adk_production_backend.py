from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import unittest

from question_bank import (
    CandidateReport, CandidateState, ConfigurationManifest, HashingTestEmbedder,
    Level, ProviderResult, ProviderUsage, ScriptedProvider,
)
from question_bank.adk_app.backend import ProductionWorkflowBackend
from question_bank.adk_app.runner import run_command
from question_bank.adk_app.workflow import BATCH_STAGE_NAMES
from question_bank.providers import ProviderFailure


def _usage() -> ProviderUsage:
    return ProviderUsage(10, 0, 10, 0, 20)


class _SameVectorEmbedder:
    checksum = "same-vector-test"

    def embed(self, texts):
        return tuple((1.0, 0.0) for _ in texts)


class ProductionBackendTests(unittest.TestCase):
    def test_adk_semantic_chunks_preserve_completed_work_after_partial_failure(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=(),
            embedding_checksum=_SameVectorEmbedder.checksum,
        )
        role = config.role("semantic_high")

        def distinct(invocation):
            return ProviderResult({"pairs": [{
                "pair_id": pair["pair_id"], "scenario": "different",
                "perspective": "different", "answer_space": "different",
                "aspect": "different", "wording": "different",
                "verdict": "distinct", "reason_codes": [],
            } for pair in invocation.payload["pairs"]]}, _usage(), role.model, "semantic-first")

        provider = ScriptedProvider({role.role: [
            distinct,
            ProviderFailure("semantic_provider_failed", ambiguous=False),
        ]})
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=_SameVectorEmbedder(),
            )
            initialized = backend.execute("campaign_initialization", {
                "campaign_id": "partial-semantic", "proposal_target": 20,
                "level": "shallow", "bank": "v2.1", "budget_usd": "1",
            }).output
            state = backend._state(initialized)
            state.passing = tuple(CandidateReport(
                candidate_id=f"semantic-candidate-{index}",
                text=f"Which ordinary object number {index} would I choose?",
                level=Level.SHALLOW, strategy="test", state=CandidateState.PROPOSED,
            ) for index in range(14))
            backend.engine._store.add_candidates(state.run_id, state.passing)
            backend.execute("local_semantic_scan", initialized)
            self.assertGreater(len(state.semantic_pairs), 6)
            backend.execute("semantic_llm_chunks", initialized)
            backend.execute("admission_decision", initialized)
            saved = backend.engine._store.candidates(state.run_id)
            backend.close()

        staged = [item for item in saved if item.state == CandidateState.STAGED]
        unresolved = [
            item for item in saved
            if item.state == CandidateState.OPERATIONALLY_UNRESOLVED
        ]
        self.assertGreater(len(staged), 1)
        self.assertGreater(len(unresolved), 0)
        self.assertEqual(2, len(provider.calls))

    def test_root_runner_executes_cancel_and_resume_routes(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = ProductionWorkflowBackend(
                root, provider=ScriptedProvider(), configuration=config,
                embedder=HashingTestEmbedder(),
            )
            backend.execute("campaign_initialization", {
                "campaign_id": "control-routes", "proposal_target": 20,
                "level": "shallow", "bank": "v2.1", "budget_usd": "0.10",
            })
            cancelled = run_command(
                "cancel campaign=control-routes", backend,
                session_root=root / ".adk-cancel",
            )
            backend.engine._store.update_campaign(
                "control-routes", status="cancelled"
            )
            resumed = run_command(
                "resume campaign=control-routes budget_usd=0.10", backend,
                session_root=root / ".adk-resume",
            )
            backend.close()

        cancel_paths = {
            event.node_info.path for event in cancelled if event.node_info
        }
        resume_paths = {
            event.node_info.path for event in resumed if event.node_info
        }
        self.assertTrue(any("/campaign_cancel@" in path for path in cancel_paths))
        self.assertTrue(any("/campaign_resume@" in path for path in resume_paths))
        self.assertTrue(any("/campaign_initialization@" in path for path in resume_paths))

    def test_cancel_can_interrupt_between_two_quality_calls(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        started = threading.Event()
        release = threading.Event()
        quality_role = config.role("quality_medium")

        def first_quality(invocation):
            started.set()
            release.wait(2)
            return ProviderResult({"records": [{
                "candidate_id": item["candidate_id"],
                "clarity": "pass", "answerability": "pass",
                "emotional_safety": "pass", "level_fit": "pass",
                "deep_revelation": "not_applicable", "reason_codes": [],
            } for item in invocation.payload["candidates"]]}, _usage(), quality_role.model, "quality-one")

        provider = ScriptedProvider({quality_role.role: [first_quality]})
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=HashingTestEmbedder(),
            )
            initialized = backend.execute("campaign_initialization", {
                "campaign_id": "cancel-quality", "proposal_target": 20,
                "level": "shallow", "bank": "v2.1", "budget_usd": "1",
            }).output
            state = backend._state(initialized)
            state.evaluation = tuple(CandidateReport(
                candidate_id=f"quality-candidate-{index}", text=f"Topic {index}?",
                level=Level.SHALLOW, strategy="test", state=CandidateState.PROPOSED,
            ) for index in range(20))
            backend.engine._store.add_candidates(state.run_id, state.evaluation)
            failure: list[BaseException] = []

            def quality_stage() -> None:
                try:
                    backend.execute("routine_quality_review", initialized)
                except BaseException as error:
                    failure.append(error)

            worker = threading.Thread(target=quality_stage)
            worker.start()
            self.assertTrue(started.wait(1))
            backend.execute("campaign_cancel", {"campaign_id": "cancel-quality"})
            release.set()
            worker.join(2)
            backend.close()

        self.assertFalse(worker.is_alive())
        self.assertEqual([], failure)
        self.assertEqual(1, len(provider.calls))

    def test_unknown_creative_spend_prevents_downstream_paid_stages(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        responses = {
            config.creative_roles[0].role: [
                ProviderFailure("connection_lost", ambiguous=True)
            ]
        }
        for slot, role in enumerate(config.creative_roles[1:], start=1):
            responses[role.role] = [ProviderResult(
                {"questions": [f"Safe topic {slot}-{index}?" for index in range(5)]},
                _usage(), role.model, f"creative-{slot}",
            )]
        provider = ScriptedProvider(responses)
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=HashingTestEmbedder(),
            )
            run_command(
                "generate campaign=unknown-spend proposal_target=20 "
                "level=shallow bank=v2.1 budget_usd=1",
                backend, session_root=Path(directory) / ".adk",
            )
            status = backend.engine._store.campaign_status("unknown-spend")
            backend.close()

        self.assertEqual("stopped", status["status"])
        self.assertEqual("unknown_spend", status["error_code"])
        self.assertTrue(all(call.role.role.startswith("creative_") for call in provider.calls))

    def test_invalid_operator_command_returns_a_structured_error(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=ScriptedProvider(), configuration=config,
                embedder=HashingTestEmbedder(),
            )
            events = run_command(
                "bogus", backend, session_root=Path(directory) / ".adk"
            )
            backend.close()
        output = next(event.output for event in events if event.output and "error" in event.output)
        self.assertIn("generate, status, cancel, or resume", output["error"])

    def test_resume_does_not_regenerate_already_persisted_creative_slots(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        responses = {}
        for slot, role in enumerate(config.creative_roles):
            responses[role.role] = [ProviderResult(
                {"questions": [f"Distinct resume topic {slot}-{index}?" for index in range(5)]},
                _usage(), role.model, f"creative-{slot}",
            )]
        provider = ScriptedProvider(responses)
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=HashingTestEmbedder(),
            )
            run_command(
                "generate campaign=resume-test proposal_target=20 "
                "level=shallow bank=v2.1 budget_usd=0.04",
                backend, session_root=Path(directory) / ".adk",
            )
            self.assertEqual("stopped", backend.engine._store.campaign_status("resume-test")["status"])
            self.assertEqual(
                4,
                sum(call.role.role.startswith("creative_") for call in provider.calls),
            )
            initial_call_count = len(provider.calls)
            prior_run_id = backend.engine._store.campaign_status("resume-test")["last_run_id"]
            active = backend.engine._store.reserve(
                prior_run_id, invocation_key="interrupted-call", role="semantic_high",
                provider="openai", model="gpt-test", reservation_usd="0.001",
                input_hash="interrupted-input",
            )
            self.assertIsNotNone(active)

            resume = backend.execute(
                "campaign_resume", {"campaign_id": "resume-test", "budget_usd": "0.20"}
            ).output
            initialized = backend.execute("campaign_initialization", resume).output
            planned = backend.execute("mission_planner", initialized).output
            outputs = [
                backend.execute(f"creative_agent_{slot + 1}", planned).output
                for slot in range(4)
            ]
            status = backend.engine._store.campaign_status("resume-test")
            recovered = backend.engine._store.ledger_summary(prior_run_id)
            backend.close()

        self.assertTrue(all(item["skipped"] == "already_persisted" for item in outputs))
        self.assertEqual(initial_call_count, len(provider.calls))
        self.assertEqual(20, status["generated_count"])
        self.assertEqual("0.001000", format(recovered.unknown_usd, "f"))
        self.assertEqual("0.000000", format(recovered.active_reserved_usd, "f"))

    def test_cancel_intent_prevents_the_next_paid_stage(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=HashingTestEmbedder(),
            )
            initialized = backend.execute("campaign_initialization", {
                "campaign_id": "cancel-me", "proposal_target": 20,
                "level": "shallow", "bank": "v2.1", "budget_usd": "1",
            }).output
            planned = backend.execute("mission_planner", initialized).output
            backend.execute("campaign_cancel", {"campaign_id": "cancel-me"})
            output = backend.execute("creative_agent_1", planned).output
            backend.close()

        self.assertEqual("cancel_requested", output["skipped"])
        self.assertEqual((), provider.calls)

    def test_scripted_campaign_executes_every_visible_stage_and_persists(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=("everyday_habits",),
            perspectives=("preference",),
        )
        words = (
            "amber", "birch", "cobalt", "dahlia", "ember",
            "fennel", "ginger", "harbor", "indigo", "juniper",
            "kiwi", "lilac", "marble", "nectarine", "opal",
            "pebble", "quartz", "robin", "saffron", "tulip",
        )
        responses: dict[str, list[ProviderResult]] = {}
        for slot, role in enumerate(config.creative_roles):
            questions = [f"{words[slot * 5 + index]}?" for index in range(5)]
            responses[role.role] = [
                ProviderResult({"questions": questions}, _usage(), role.model, f"creative-{slot}")
            ]
        quality_role = config.role("quality_medium")
        quality_responses = []
        for offset in (0, 10):
            records = [
                {
                    "candidate_id": "filled-by-callback",
                    "clarity": "pass", "answerability": "pass",
                    "emotional_safety": "pass", "level_fit": "pass",
                    "deep_revelation": "not_applicable", "reason_codes": [],
                }
                for _ in range(10)
            ]

            def quality(invocation, records=records, offset=offset):
                for record, candidate in zip(records, invocation.payload["candidates"], strict=True):
                    record["candidate_id"] = candidate["candidate_id"]
                return ProviderResult(
                    {"records": records}, _usage(), quality_role.model,
                    f"quality-{offset}",
                )

            quality_responses.append(quality)
        responses[quality_role.role] = quality_responses
        semantic_role = config.role("semantic_high")

        def semantic(invocation):
            pairs = [
                {
                    "pair_id": item["pair_id"], "scenario": "different",
                    "perspective": "different", "answer_space": "different",
                    "aspect": "different", "wording": "different",
                    "verdict": "distinct", "reason_codes": [],
                }
                for item in invocation.payload["pairs"]
            ]
            return ProviderResult(
                {"pairs": pairs}, _usage(), semantic_role.model, "semantic"
            )

        responses[semantic_role.role] = [semantic for _ in range(100)]
        observation_role = config.role("observed_diversity")

        def observation(invocation):
            missions = [
                {
                    "agent_slot": slot, "level": "shallow",
                    "brief": f"Explore a distinct ordinary subject {slot}.",
                    "aspect": None, "scenario": None, "perspective": None,
                    "contrast": None, "theme_hints": [],
                }
                for slot in range(4)
            ]
            return ProviderResult(
                {"observations": [], "avoid_patterns": [],
                 "explore_directions": [], "next_missions": missions},
                _usage(), observation_role.model, "observation",
            )

        responses[observation_role.role] = [observation]
        metadata_role = config.role("metadata_medium")

        def metadata(invocation):
            records = [
                {
                    "candidate_id": item["candidate_id"], "themes": [],
                    "themes_resolved": True, "aspect": "everyday_habits",
                    "perspective": "preference", "scenario": "ordinary day",
                    "answer_space": "one familiar choice", "wording": "direct",
                    "uncertain_fields": [],
                }
                for item in invocation.payload["questions"]
            ]
            return ProviderResult(
                {"records": records}, _usage(), metadata_role.model, "metadata"
            )

        responses[metadata_role.role] = [metadata]
        provider = ScriptedProvider(responses)

        with tempfile.TemporaryDirectory() as directory:
            backend = ProductionWorkflowBackend(
                Path(directory), provider=provider, configuration=config,
                embedder=HashingTestEmbedder(),
            )

            events = run_command(
                "generate campaign=scripted proposal_target=20 "
                "level=shallow bank=v2.1 budget_usd=1",
                backend, session_root=Path(directory) / ".adk",
            )
            status = backend.engine._store.campaign_status("scripted")
            spend_status = backend.execute(
                "campaign_status", {"campaign_id": "scripted"}
            ).output
            self.assertTrue((Path(directory) / ".adk" / "sessions.sqlite3").exists())
            backend.close()

        paths = {event.node_info.path for event in events if event.node_info}
        for stage in BATCH_STAGE_NAMES:
            self.assertTrue(any(f"/{stage}@" in path for path in paths), stage)
        self.assertEqual("completed", status["status"], status)
        self.assertEqual(20, status["generated_count"])
        self.assertEqual(20, status["staged_count"])
        self.assertIn("remaining_usd", spend_status["spend"])


if __name__ == "__main__":
    unittest.main()
