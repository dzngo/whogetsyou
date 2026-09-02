from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from question_bank import CandidateState, HumanReview
from question_bank.contracts import (
    CandidateReport,
    ConfigurationManifest,
    Level,
    RunRequest,
)
from question_bank.store import V2Store


class HumanReviewTests(unittest.TestCase):
    def test_metadata_resolution_updates_only_allowed_fields_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = V2Store(root)
            config = ConfigurationManifest.approved_defaults(
                named_themes=("Work",),
                aspects=("identity",),
                perspectives=("memory",),
            )
            store.install_configuration(config)
            request = RunRequest.pilot(
                idempotency_key="metadata-review", snapshot_id=store.ensure_empty_snapshot()
            )
            run_id, _ = store.create_run(request, config.manifest_id)
            candidate = CandidateReport(
                "candidate-metadata",
                "Which work memory still shapes you?",
                Level.DEEP,
                "inner_signals",
                CandidateState.STAGED,
                theme_memberships=None,
                metadata={
                    "themes_resolved": False,
                    "aspect": None,
                    "perspective": None,
                    "scenario": None,
                    "answer_space": None,
                    "wording": None,
                    "uncertain_fields": (
                        "themes", "aspect", "perspective", "scenario",
                        "answer_space", "wording",
                    ),
                },
            )
            store.add_candidates(run_id, (candidate,))
            case_id = store.open_review_case(
                run_id=run_id,
                candidate_id=candidate.candidate_id,
                review_kind="metadata_uncertainty",
                priority=30,
                packet={"configuration_id": config.manifest_id, "text": candidate.text},
            )
            store.close()
            review = HumanReview(root)

            review.resolve(
                case_id,
                {
                    "action": "accept",
                    "metadata": {
                        "themes": ["Work"],
                        "aspect": "identity",
                        "perspective": "memory",
                        "scenario": "formative work memory",
                        "answer_space": "lasting influence",
                        "wording": "which memory",
                    },
                },
                idempotency_key="metadata-resolution",
            )

            resolved = review.run_report(run_id).candidates[0]
            self.assertEqual(("Work",), resolved.theme_memberships)
            self.assertEqual((), resolved.metadata["uncertain_fields"])
            self.assertEqual("identity", resolved.metadata["aspect"])
            review.close()

    def test_resolutions_are_idempotent_and_a_spot_check_defect_blocks_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = V2Store(root)
            config = ConfigurationManifest.approved_defaults(
                named_themes=("Work",), aspects=("identity",), perspectives=("memory",)
            )
            store.install_configuration(config)
            snapshot_id = store.ensure_empty_snapshot()
            request = RunRequest.pilot(idempotency_key="review", snapshot_id=snapshot_id)
            run_id, _ = store.create_run(request, config.manifest_id)
            candidate = CandidateReport(
                "candidate-one", "What small choice reveals you?", Level.SHALLOW,
                "concrete_life_moments", CandidateState.STAGED, theme_memberships=(),
                metadata={"themes_resolved": True, "aspect": "identity", "perspective": "memory", "scenario": "choice", "answer_space": "preference", "wording": "what"},
            )
            store.add_candidates(run_id, (candidate,))
            case_id = store.open_review_case(
                run_id=run_id, candidate_id=candidate.candidate_id,
                review_kind="protected_spot_check", priority=100,
                packet={"text": candidate.text},
            )
            store.set_run_state(run_id, "awaiting_human_review", "pilot_spot_check")
            store.close()

            review = HumanReview(root)
            first = review.resolve(
                case_id, {"action": "fail", "reason_codes": ["unclear"]},
                idempotency_key="resolution-one",
            )
            repeated = review.resolve(
                case_id, {"action": "fail", "reason_codes": ["unclear"]},
                idempotency_key="resolution-one",
            )

            self.assertEqual(first, repeated)
            self.assertEqual("resolved", first["status"])
            self.assertEqual("redesign_required", review.run_report(run_id).stop_reason)
            self.assertEqual(CandidateState.REJECTED, review.run_report(run_id).candidates[0].state)
            review.close()

    def test_review_cannot_edit_question_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = V2Store(root)
            config = ConfigurationManifest.approved_defaults(
                named_themes=(), aspects=(), perspectives=()
            )
            store.install_configuration(config)
            snapshot_id = store.ensure_empty_snapshot()
            request = RunRequest.pilot(idempotency_key="edit", snapshot_id=snapshot_id)
            run_id, _ = store.create_run(request, config.manifest_id)
            candidate = CandidateReport(
                "candidate-edit", "Original question?", Level.DEEP, "inner_signals", CandidateState.AWAITING_HUMAN_REVIEW
            )
            store.add_candidates(run_id, (candidate,))
            case_id = store.open_review_case(
                run_id=run_id, candidate_id=candidate.candidate_id,
                review_kind="quality_uncertainty", priority=20, packet={"text": candidate.text},
            )
            store.close()
            review = HumanReview(root)
            with self.assertRaisesRegex(ValueError, "edit"):
                review.resolve(case_id, {"action": "accept", "text": "Edited?"}, idempotency_key="bad-edit")
            review.close()


if __name__ == "__main__":
    unittest.main()
