import tempfile
import unittest
from pathlib import Path

from question_bank.contracts import (
    DEFAULT_POLICY_VERSIONS,
    AdmissionDecision,
    CoverageRegion,
    CoverageRegionKind,
    HumanResolution,
    QuestionLevel,
    QuestionUsageEvent,
    ReleaseIntent,
    ReviewRequest,
    TaxonomyCandidate,
)
from question_bank.core import QuestionBank
from question_bank.modules import (
    CompletionChallenge,
    CoveragePlanner,
    HumanReview,
    QuestionBankNeighborIndex,
    QuestionUsageSink,
    ReferenceExampleRegistry,
    ReleaseModule,
    TaxonomyRegistry,
)
from tests.question_bank.test_core import accepted_package


class ModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.bank = QuestionBank(root / "bank.sqlite3")
        self.workflow_db = root / "workflow.sqlite3"

    def tearDown(self) -> None:
        self.bank.close()
        self.tempdir.cleanup()

    def test_neighbor_index_returns_evidence_not_verdicts(self) -> None:
        revision = self.bank.admit(accepted_package())
        snapshot = self.bank.snapshot({"revision_ids": [revision.revision_id]})
        index = QuestionBankNeighborIndex(self.bank)
        evidence = index.find_neighbors(
            {
                "text": "Which little ritual helps you return to yourself?",
                "scenario": "returning to oneself after a difficult day",
                "perspective_id": "restoration",
                "answer_space": "a personally meaningful repeatable ritual",
            },
            snapshot.snapshot_id,
        )
        self.assertEqual(revision.revision_id, evidence[0].neighbor_revision_id)
        self.assertFalse(hasattr(evidence[0], "semantic_repeat"))

    def test_review_resolution_is_immutable_and_idempotent(self) -> None:
        review = HumanReview(self.workflow_db)
        case = review.open_case(
            ReviewRequest("req-1", "open-1", "admission", "proposal-1", {"reason_codes": ["uncertain"]})
        )
        resolution = HumanResolution("resolve-1", "accept", ["human_confirmed"])
        first = review.resolve(case.case_id, resolution)
        second = review.resolve(case.case_id, resolution)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "already resolved"):
            review.resolve(case.case_id, HumanResolution("resolve-2", "reject", ["unsafe"]))
        review.close()

    def test_taxonomy_requires_six_distinct_supports_and_release(self) -> None:
        registry = TaxonomyRegistry(self.workflow_db)
        base = registry.install_initial(
            "base-taxonomy",
            ["self_understanding"],
            ["restoration"],
        )
        weak = TaxonomyCandidate("tc-1", "tc-key-1", "aspect", "Ritual", "Personal rituals", ["c1"])
        self.assertEqual(AdmissionDecision.HUMAN_REVIEW, registry.evaluate_candidate(weak, {}).decision)
        strong = TaxonomyCandidate(
            "tc-2", "tc-key-2", "aspect", "Restoration", "Ways people return to themselves", [f"c{i}" for i in range(6)]
        )
        decision = registry.evaluate_candidate(strong, {"specialists_passed": True, "challenger_passed": True, "shadow_agreement": 2})
        self.assertEqual(AdmissionDecision.ACCEPT, decision.decision)
        version = registry.release(
            {
                "idempotency_key": "tax-release-1",
                "candidate_ids": ["tc-2"],
                "base_version_id": base.version_id,
            }
        )
        self.assertTrue(version.released)
        self.assertIn("restoration", version.aspects)
        self.assertIn("self_understanding", version.aspects)
        registry.close()

    def test_coverage_requires_three_distinct_scenarios(self) -> None:
        revision = self.bank.admit(accepted_package())
        snapshot = self.bank.snapshot({"revision_ids": [revision.revision_id]})
        planner = CoveragePlanner(self.workflow_db, self.bank)
        plan = planner.plan(
            {
                "version_id": "taxonomy-v1",
                "regions": [
                    CoverageRegion(
                        "region-1", "identity", QuestionLevel.DEEP, "self_understanding", "restoration", CoverageRegionKind.REQUIRED
                    )
                ],
            }
        )
        report = planner.measure(snapshot.snapshot_id, plan.plan_id)
        self.assertEqual(("region-1",), report.gaps)
        briefs = planner.next_gaps(report)
        self.assertEqual("region-1", briefs[0].coverage_gap["region_id"])
        planner.close()

    def test_completion_requires_three_saturated_rounds_and_two_strategies(self) -> None:
        challenge = CompletionChallenge()
        rounds = [
            {
                "strategies": [
                    {"concepts": 20, "accepted_distinct": 0, "new_valid_regions": 0, "dominant_rejection": "semantic_repeat"},
                    {"concepts": 20, "accepted_distinct": 0, "new_valid_regions": 0, "dominant_rejection": "semantic_repeat"},
                ]
            }
            for _ in range(3)
        ]
        self.assertTrue(challenge.is_complete(True, rounds))
        rounds[0]["strategies"][0]["accepted_distinct"] = 1
        self.assertFalse(challenge.is_complete(True, rounds))

    def test_coverage_rejects_scenario_depth_with_repeated_answer_space_and_wording(self) -> None:
        revisions = []
        for index in range(3):
            package = accepted_package(f"coverage-admit-{index}")
            proposal_id = f"coverage-proposal-{index}"
            package.proposal.proposal_id = proposal_id
            package.proposal.text = f"What ritual number {index} helps you reset?"
            package.proposal.semantic_scenario = f"distinct scenario {index}"
            package.evidence.evidence_id = f"coverage-evidence-{index}"
            package.evidence.proposal_id = proposal_id
            package.evidence.resolved_facets["semantic_scenario"] = package.proposal.semantic_scenario
            package.outcome.outcome_id = f"coverage-outcome-{index}"
            package.outcome.proposal_id = proposal_id
            package.outcome.evidence_id = package.evidence.evidence_id
            package.theme_classification.classification_id = f"coverage-themes-{index}"
            package.theme_classification.proposal_id = proposal_id
            revisions.append(self.bank.admit(package))
        snapshot = self.bank.snapshot(
            {"revision_ids": [revision.revision_id for revision in revisions]}
        )
        planner = CoveragePlanner(self.workflow_db, self.bank)
        plan = planner.plan(
            {
                "version_id": "taxonomy-v1",
                "regions": [
                    CoverageRegion(
                        "region-repeat",
                        "identity",
                        QuestionLevel.DEEP,
                        "self_understanding",
                        "restoration",
                        CoverageRegionKind.REQUIRED,
                    )
                ],
            }
        )
        report = planner.measure(snapshot.snapshot_id, plan.plan_id, include_staged=True)
        self.assertIn("region-repeat", report.gaps)
        self.assertIn("region:region-repeat:answer_space", report.concentration_alerts)
        self.assertIn("region:region-repeat:wording_pattern", report.concentration_alerts)
        planner.close()

    def test_release_verifies_hash_and_rolls_back_atomically(self) -> None:
        taxonomy = TaxonomyRegistry(self.workflow_db)
        taxonomy_version = taxonomy.install_initial(
            "initial-taxonomy",
            ["self_understanding"],
            ["restoration"],
        )
        package = accepted_package()
        package.taxonomy_version_id = taxonomy_version.version_id
        revision = self.bank.admit(package)
        coverage = CoveragePlanner(self.workflow_db, self.bank)
        plan = coverage.plan(
            {
                "version_id": taxonomy_version.version_id,
                "regions": [
                    CoverageRegion(
                        "region-exploratory",
                        "identity",
                        QuestionLevel.DEEP,
                        "self_understanding",
                        "restoration",
                        CoverageRegionKind.EXPLORATORY,
                    )
                ],
            }
        )
        references = ReferenceExampleRegistry(self.workflow_db)
        examples = [
            {
                "example_id": f"reference-{index}",
                "question": f"Reference question {index}?",
                "expected_decision": "accept" if index % 2 else "reject",
            }
            for index in range(30)
        ]
        references.import_examples(examples, confirmed=True)
        policies = dict(DEFAULT_POLICY_VERSIONS)
        references.record_regression(
            policies,
            {example["example_id"]: True for example in examples},
        )
        release = ReleaseModule(
            self.workflow_db,
            self.bank,
            taxonomy,
            coverage,
            references,
            lambda revisions, packages, snapshot_id, intent: {
                "quality_revalidation": True,
                "whole_bank_relation_revalidation": True,
            },
        )
        candidate = release.build_candidate(
            ReleaseIntent(
                "release-1",
                [revision.revision_id],
                taxonomy_version.version_id,
                plan.plan_id,
                policies,
                True,
            )
        )
        self.assertTrue(release.verify(candidate.snapshot_id).passed)
        published = release.publish(candidate.snapshot_id)
        self.assertEqual("released", published.status)
        rolled_back = release.rollback(candidate.snapshot_id)
        self.assertEqual(candidate.snapshot_id, rolled_back.snapshot_id)
        duplicate = accepted_package("admit-semantic-repeat")
        duplicate.taxonomy_version_id = taxonomy_version.version_id
        duplicate.proposal.proposal_id = "proposal-semantic-repeat"
        duplicate.proposal.text = "Which small ritual makes you feel like yourself again?"
        duplicate.evidence.proposal_id = duplicate.proposal.proposal_id
        duplicate.evidence.evidence_id = "evidence-semantic-repeat"
        duplicate.outcome.proposal_id = duplicate.proposal.proposal_id
        duplicate.outcome.outcome_id = "outcome-semantic-repeat"
        duplicate.outcome.evidence_id = duplicate.evidence.evidence_id
        duplicate.theme_classification.proposal_id = duplicate.proposal.proposal_id
        duplicate.theme_classification.classification_id = "themes-semantic-repeat"
        duplicate_revision = self.bank.admit(duplicate)
        unsafe_candidate = release.build_candidate(
            ReleaseIntent(
                "release-semantic-repeat",
                [revision.revision_id, duplicate_revision.revision_id],
                taxonomy_version.version_id,
                plan.plan_id,
                policies,
                True,
            )
        )
        unsafe_report = release.verify(unsafe_candidate.snapshot_id)
        self.assertFalse(unsafe_report.gate_results["semantic_facet_distinctness"])
        release.close()
        references.close()
        coverage.close()
        taxonomy.close()

    def test_usage_sink_is_separate_idempotent_and_rejects_private_data(self) -> None:
        sink = QuestionUsageSink(Path(self.tempdir.name) / "usage.sqlite3")
        event = QuestionUsageEvent(
            "event-1", "usage-key-1", "presented", "session-opaque", "snapshot-1", "q-1", "qr-1",
            "round-1", "presentation-1", "identity", "deep", "en", "bank",
        )
        self.assertTrue(sink.append(event)["appended"])
        self.assertFalse(sink.append(event)["appended"])
        event.origin = "bank;answer=secret"
        with self.assertRaisesRegex(ValueError, "origin"):
            sink.append(event)
        sink.close()


if __name__ == "__main__":
    unittest.main()
