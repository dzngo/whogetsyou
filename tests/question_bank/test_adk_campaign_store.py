from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from question_bank.store import V2Store
from question_bank.contracts import (
    CandidateReport, CandidateState, ConfigurationManifest, Level, RunRequest,
)


class CampaignStoreTests(unittest.TestCase):
    def test_candidate_persistence_and_campaign_count_are_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = V2Store(Path(directory))
            store.create_campaign(
                campaign_id="atomic", proposal_target=20, level="shallow",
                bank="v2.1", budget_usd=Decimal("1"),
                configuration_id="configuration", execution_token="owner",
            )
            configuration = ConfigurationManifest.approved_defaults(
                named_themes=(), aspects=(), perspectives=()
            )
            store.install_configuration(configuration)
            snapshot_id = store.ensure_empty_snapshot()
            request = RunRequest.production_batch(
                idempotency_key="atomic-run", snapshot_id=snapshot_id,
                batch_index=0, authorization_usd=Decimal("1"),
                configuration_id=configuration.manifest_id,
            )
            run_id, _ = store.create_run(request, configuration.manifest_id)
            candidate = CandidateReport(
                candidate_id="candidate-one", text="What is my favorite color?",
                level=Level.SHALLOW, strategy="direct",
                state=CandidateState.PROPOSED,
            )
            first = store.persist_campaign_candidates(
                "atomic", run_id, (candidate,), execution_token="owner"
            )
            second = store.persist_campaign_candidates(
                "atomic", run_id, (candidate,), execution_token="owner"
            )
            status = store.campaign_status("atomic")
            store.close()

        self.assertEqual((1, 0), (first, second))
        self.assertEqual(1, status["generated_count"])

    def test_campaign_control_state_is_durable_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = V2Store(root)
            created = store.create_campaign(
                campaign_id="campaign-one",
                proposal_target=40,
                level="shallow",
                bank="v2.1",
                budget_usd=Decimal("0.25"),
                configuration_id="configuration-one",
            )
            self.assertTrue(created)
            store.update_campaign(
                "campaign-one",
                active_stage="mission_planner",
                batch_index=1,
                generated_count=20,
                staged_count=7,
                last_run_id="run-one",
            )
            store.request_campaign_cancel("campaign-one")
            store.close()

            reopened = V2Store(root)
            status = reopened.campaign_status("campaign-one")
            events = reopened.campaign_events("campaign-one")
            reopened.close()

        self.assertEqual("cancel_requested", status["status"])
        self.assertEqual("mission_planner", status["active_stage"])
        self.assertEqual(20, status["generated_count"])
        self.assertEqual(7, status["staged_count"])
        self.assertEqual("run-one", status["last_run_id"])
        self.assertTrue(status["cancel_requested"])
        self.assertEqual(["created", "progress", "cancel_requested"], [event["event_type"] for event in events])

    def test_resume_adds_fresh_authorization_and_clears_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = V2Store(Path(directory))
            store.create_campaign(
                campaign_id="campaign-two",
                proposal_target=20,
                level="deep",
                bank="v2.1",
                budget_usd=Decimal("0.10"),
                configuration_id="configuration-two",
            )
            store.request_campaign_cancel("campaign-two")
            store.update_campaign("campaign-two", status="cancelled")
            store.resume_campaign(
                "campaign-two", Decimal("0.15"),
                expected_configuration_id="configuration-two",
            )
            status = store.campaign_status("campaign-two")
            store.close()

        self.assertEqual("running", status["status"])
        self.assertFalse(status["cancel_requested"])
        self.assertEqual("0.250000", status["authorized_usd"])
        self.assertEqual(240, status["attempt_limit"])

    def test_resume_rejects_an_incompatible_configuration_without_adding_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = V2Store(Path(directory))
            store.create_campaign(
                campaign_id="configuration-guard", proposal_target=20,
                level="deep", bank="v2.1", budget_usd=Decimal("0.10"),
                configuration_id="original",
            )
            store.update_campaign("configuration-guard", status="stopped")
            with self.assertRaisesRegex(ValueError, "another configuration"):
                store.resume_campaign(
                    "configuration-guard", Decimal("0.15"),
                    expected_configuration_id="different",
                )
            status = store.campaign_status("configuration-guard")
            store.close()

        self.assertEqual("stopped", status["status"])
        self.assertEqual("0.100000", status["authorized_usd"])


if __name__ == "__main__":
    unittest.main()
