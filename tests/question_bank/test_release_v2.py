from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from question_bank.contracts import (
    CandidateReport,
    CandidateState,
    ConfigurationManifest,
    Level,
    RunMode,
    RunRequest,
)
from question_bank.regression import ReferenceFixture
from question_bank.release import ReleaseModule
from question_bank.store import V2Store


class BasisEmbedder:
    model_id = "BAAI/bge-small-en-v1.5"
    dimensions = 384
    checksum = "basis-fixture"

    def embed(self, texts):
        result = []
        for index, _ in enumerate(texts):
            vector = [0.0] * self.dimensions
            vector[index % self.dimensions] = 1.0
            result.append(tuple(vector))
        return result


class ReleaseModuleTests(unittest.TestCase):
    def test_release_reports_metadata_collapse_even_before_minimum_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = ConfigurationManifest.approved_defaults(
                named_themes=(),
                aspects=("identity",),
                perspectives=("memory",),
                embedding_checksum="basis-fixture",
                local_distance_authority=True,
            )
            store = V2Store(root)
            store.install_configuration(configuration)
            request = RunRequest.production_batch(
                idempotency_key="collapse-production",
                snapshot_id=store.ensure_empty_snapshot(),
                batch_index=0,
                configuration_id=configuration.manifest_id,
            )
            run_id, _ = store.create_run(request, configuration.manifest_id)
            candidate = CandidateReport(
                "candidate-collapse",
                "Which quiet choice says the most about you?",
                Level.DEEP,
                "inner_signals",
                CandidateState.STAGED,
                theme_memberships=(),
                metadata={
                    "themes_resolved": True,
                    "aspect": "identity",
                    "perspective": "memory",
                    "scenario": "quiet choice",
                    "answer_space": "personal value",
                    "wording": "which choice",
                    "uncertain_fields": (),
                },
            )
            store.add_candidates(run_id, (candidate,))
            for evidence_type in ("quality", "semantic_gate"):
                store.add_evidence(
                    run_id=run_id,
                    candidate_id=candidate.candidate_id,
                    evidence_type=evidence_type,
                    configuration_id=configuration.manifest_id,
                    payload={"deterministic_outcome": "pass"},
                )
            store.set_run_state(run_id, "completed", "batch_complete")
            store.close()
            release = ReleaseModule(
                root, configuration=configuration, embedder=BasisEmbedder()
            )

            snapshot_id = release.build_candidate_snapshot(
                run_id, idempotency_key="collapse-snapshot"
            )
            report = release.verify(snapshot_id)

            self.assertIn("minimum_question_count", report.blockers)
            self.assertIn("diversity_collapse:aspect", report.blockers)
            self.assertIn("diversity_collapse:perspective", report.blockers)
            release.close()

    def test_provider_free_verify_publish_withdraw_and_rollback_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = ConfigurationManifest.approved_defaults(
                named_themes=("Work",),
                aspects=tuple(f"aspect-{index}" for index in range(5)),
                perspectives=tuple(f"perspective-{index}" for index in range(4)),
                embedding_checksum="basis-fixture",
                local_distance_authority=True,
            )
            store = V2Store(root)
            store.install_configuration(configuration)
            empty = store.ensure_empty_snapshot()
            request = RunRequest(
                "production-fixture", RunMode.PRODUCTION, empty, 200,
                (Level.SHALLOW, Level.DEEP), configuration.role("quality_medium").reservation_usd * 0 + 2,
                100, 6, 4, configuration.manifest_id,
            )
            run_id, _ = store.create_run(request, configuration.manifest_id)
            candidates = tuple(
                CandidateReport(
                    f"candidate-{index}",
                    "Which "
                    + " ".join(
                        hashlib.sha256(f"{index}-{part}".encode()).hexdigest()[part : part + 8]
                        for part in range(10)
                    )
                    + " matters?",
                    Level.SHALLOW if index % 2 == 0 else Level.DEEP,
                    configuration.creative_roles[index % 4].role.removeprefix("creative_"),
                    CandidateState.STAGED, ("quality_and_semantic_pass",), (),
                    {
                        "themes_resolved": True,
                        "aspect": f"aspect-{index % 5}",
                        "perspective": f"perspective-{index % 4}",
                        "scenario": f"scenario-{index}",
                        "answer_space": f"answer-{index % 5}",
                        "wording": f"wording-{index % 4}",
                        "uncertain_fields": (),
                    },
                )
                for index in range(200)
            )
            store.add_candidates(run_id, candidates)
            store.set_run_state(run_id, "completed", "batch_complete")
            for candidate in candidates:
                store.add_evidence(
                    run_id=run_id, candidate_id=candidate.candidate_id,
                    evidence_type="quality", configuration_id=configuration.manifest_id,
                    payload={"deterministic_outcome": "pass"},
                )
                store.add_evidence(
                    run_id=run_id, candidate_id=candidate.candidate_id,
                    evidence_type="semantic_gate", configuration_id=configuration.manifest_id,
                    payload={"deterministic_outcome": "pass"},
                )
            store.close()

            release = ReleaseModule(root, configuration=configuration, embedder=BasisEmbedder())
            snapshot_id = release.build_candidate_snapshot(
                run_id, idempotency_key="snapshot-one"
            )
            self.assertEqual(
                snapshot_id,
                release.build_candidate_snapshot(run_id, idempotency_key="snapshot-one"),
            )
            before = release.verify(snapshot_id)
            self.assertIn("missing_regression", before.blockers)
            self.assertIn("missing_spot_check", before.blockers)

            release.record_regression(snapshot_id, fixture_hash=ReferenceFixture.load_default().fixture_hash, passed=True, signature="human-a")
            release.record_spot_check(
                snapshot_id,
                question_ids=release.select_spot_check(snapshot_id),
                passed=True,
                signature="human-b",
            )
            verified = release.verify(snapshot_id)
            self.assertTrue(verified.passed)
            published = release.publish(snapshot_id, idempotency_key="publish-one")
            withdrawn = release.withdraw(reason="operator withdrawal", idempotency_key="withdraw-one")
            restored = release.rollback(snapshot_id, idempotency_key="rollback-one")

            self.assertEqual(snapshot_id, published.snapshot_id)
            self.assertIsNone(withdrawn.snapshot_id)
            self.assertEqual(snapshot_id, restored.snapshot_id)
            self.assertEqual(restored, release.rollback(snapshot_id, idempotency_key="rollback-one"))
            with self.assertRaisesRegex(ValueError, "different release action"):
                release.withdraw(reason="conflict", idempotency_key="publish-one")
            release.close()


if __name__ == "__main__":
    unittest.main()
