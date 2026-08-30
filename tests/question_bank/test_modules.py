import sqlite3
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
    SpotCheckRegistry,
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
        with sqlite3.connect(self.workflow_db) as connection:
            outcome_id = connection.execute(
                "SELECT outcome_id FROM human_admission_outcomes WHERE case_id = ?",
                (case.case_id,),
            ).fetchone()[0]
        self.assertEqual(f"human-outcome-{first.resolution_id}", outcome_id)
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
        decision = registry.evaluate_candidate(
            strong,
            {
                "specialists_passed": True,
                "challenger_passed": True,
                "shadow_agreement": 2,
                "distinct_scenarios": 3,
                "distinct_perspectives": 2,
                "distinct_answer_spaces": 2,
                "distinct_scouts": 2,
            },
        )
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
        context = registry.definition_context(version.version_id)
        restoration = next(
            taxon for taxon in context["aspects"] if taxon["id"] == "restoration"
        )
        self.assertEqual("Ways people return to themselves", restoration["definition"])
        self.assertTrue(registry.is_ancestor_or_same(base.version_id, version.version_id))
        registry.close()

    def test_taxonomy_activation_requires_plan_and_exact_regression(self) -> None:
        registry = TaxonomyRegistry(self.workflow_db)
        base = registry.install_initial("base", ["identity"], ["reflection"])
        candidate = TaxonomyCandidate(
            "tc-staged",
            "tc-staged-key",
            "aspect",
            "Restoration",
            "Ways people return to a settled sense of self",
            [f"support-{index}" for index in range(6)],
        )
        registry.evaluate_candidate(
            candidate,
            {
                "specialists_passed": True,
                "challenger_passed": True,
                "shadow_agreement": 2,
                "distinct_scenarios": 3,
                "distinct_perspectives": 2,
                "distinct_answer_spaces": 2,
                "distinct_scouts": 2,
            },
        )
        staged = registry.release(
            {
                "idempotency_key": "stage-taxonomy",
                "candidate_ids": [candidate.candidate_id],
                "base_version_id": base.version_id,
            },
            staged=True,
        )
        self.assertFalse(staged.released)
        self.assertEqual(base.version_id, registry.current_version().version_id)
        planner = CoveragePlanner(self.workflow_db, self.bank)
        plan = planner.plan(
            {
                "version_id": staged.version_id,
                "regions": [
                    CoverageRegion(
                        "staged-region",
                        "identity",
                        QuestionLevel.DEEP,
                        "restoration",
                        "reflection",
                        CoverageRegionKind.EXPLORATORY,
                    )
                ],
            }
        )
        references = ReferenceExampleRegistry(self.workflow_db, minimum_confirmed=1)
        references.import_examples(
            [
                {
                    "example_id": "ref-one",
                    "question": "What restores you?",
                    "expected_decision": "accept",
                }
            ],
            confirmed=True,
        )
        policies = dict(DEFAULT_POLICY_VERSIONS)
        regression_id = references.record_regression(
            policies, {"ref-one": True}, staged.version_id
        )
        activated = registry.activate_staged(
            staged.version_id, plan.plan_id, regression_id, policies
        )
        self.assertTrue(activated.released)
        self.assertEqual(staged.version_id, registry.current_version().version_id)
        references.close()
        planner.close()
        registry.close()

    def test_split_uses_verified_multi_taxon_projection_package(self) -> None:
        registry = TaxonomyRegistry(self.workflow_db)
        base = registry.install_initial("split-base", ["identity"], ["reflection"])
        candidate = TaxonomyCandidate(
            "tc-split",
            "tc-split-key",
            "aspect",
            "Identity split",
            "Separate stable self-concept from changing self-expression",
            [f"support-{index}" for index in range(6)],
            affected_taxon_ids=["identity"],
            proposed_operation="split",
            replacement_taxa=[
                {"label": "Self concept", "definition": "Stable views of oneself"},
                {
                    "label": "Self expression",
                    "definition": "Ways identity is expressed and changed",
                },
            ],
        )
        decision = registry.evaluate_candidate(
            candidate,
            {
                "specialists_passed": True,
                "challenger_passed": True,
                "shadow_agreement": 2,
                "distinct_scenarios": 3,
                "distinct_perspectives": 2,
                "distinct_answer_spaces": 2,
                "distinct_scouts": 2,
            },
        )
        self.assertEqual(AdmissionDecision.HUMAN_REVIEW, decision.decision)
        registry.attach_verified_change_package(
            candidate.candidate_id,
            {
                "affected_revision_ids": [],
                "reclassification_plan": {},
                "revalidation_evidence_ids": [],
            },
        )
        registry.resolve_human_candidate(candidate.candidate_id, "accept")
        staged = registry.release(
            {
                "idempotency_key": "split-stage",
                "candidate_ids": [candidate.candidate_id],
                "base_version_id": base.version_id,
            },
            staged=True,
        )
        manifest = registry.manifest_record(staged.version_id, allow_staged=True)
        self.assertEqual(
            ["self_concept", "self_expression"],
            manifest["taxa"]["aspect"]["identity"]["replaced_by"],
        )
        self.assertIn("self_concept", manifest["aspects"])
        self.assertIn("self_expression", manifest["aspects"])
        registry.close()

    def test_spot_check_requires_ten_passed_candidate_revisions(self) -> None:
        registry = SpotCheckRegistry(self.workflow_db)
        policies = dict(DEFAULT_POLICY_VERSIONS)
        with self.assertRaisesRegex(ValueError, "exactly ten"):
            registry.record(
                "short-check",
                policies,
                {
                    "checks": [{"revision_id": "qr-1", "passed": True}],
                    "candidate_revision_ids": ["qr-1"],
                    "reviewer_id": "reviewer-a",
                    "selection_method": "random",
                    "selection_seed": "seed-a",
                },
            )
        checks = [
            {"revision_id": f"qr-{index}", "passed": True}
            for index in range(10)
        ]
        spot_check_id = registry.record(
            "ten-check",
            policies,
            {
                "checks": checks,
                "candidate_revision_ids": [f"qr-{index}" for index in range(10)],
                "reviewer_id": "reviewer-a",
                "selection_method": "random",
                "selection_seed": "seed-a",
            },
        )
        record = registry.passed_record(
            spot_check_id,
            policies,
            [f"qr-{index}" for index in range(10)],
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(10, record["question_count"])
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

    def test_production_coverage_plan_must_classify_the_complete_matrix(self) -> None:
        registry = TaxonomyRegistry(self.workflow_db)
        version = registry.install_initial(
            "coverage-matrix-taxonomy",
            ["self_understanding"],
            ["restoration"],
        )
        planner = CoveragePlanner(
            self.workflow_db,
            self.bank,
            registry,
            ["identity", "family"],
        )
        incomplete = [
            CoverageRegion(
                "only-one",
                "identity",
                QuestionLevel.DEEP,
                "self_understanding",
                "restoration",
                CoverageRegionKind.REQUIRED,
            )
        ]
        with self.assertRaisesRegex(ValueError, "classify every"):
            planner.plan({"version_id": version.version_id, "regions": incomplete})
        planner.close()
        registry.close()

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
        descendant_candidate = TaxonomyCandidate(
            "release-taxonomy-candidate",
            "release-taxonomy-candidate-key",
            "aspect",
            "Daily Rhythm",
            "The recurring shape of an ordinary day",
            [f"release-support-{index}" for index in range(6)],
        )
        taxonomy.evaluate_candidate(
            descendant_candidate,
            {
                "specialists_passed": True,
                "challenger_passed": True,
                "shadow_agreement": 2,
                "distinct_scenarios": 3,
                "distinct_perspectives": 2,
                "distinct_answer_spaces": 2,
                "distinct_scouts": 2,
            },
        )
        release_taxonomy = taxonomy.release(
            {
                "idempotency_key": "release-descendant-taxonomy",
                "candidate_ids": [descendant_candidate.candidate_id],
                "base_version_id": taxonomy_version.version_id,
            }
        )
        coverage = CoveragePlanner(self.workflow_db, self.bank)
        plan = coverage.plan(
            {
                "version_id": release_taxonomy.version_id,
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
            release_taxonomy.version_id,
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
                release_taxonomy.version_id,
                plan.plan_id,
                policies,
                True,
            )
        )
        self.assertTrue(release.verify(candidate.snapshot_id).passed)
        audit = release.audit_manifest(candidate.snapshot_id)
        self.assertEqual(release_taxonomy.version_id, audit["taxonomy_version_id"])
        self.assertTrue(audit["reference_regression"]["passed"])
        self.assertTrue(audit["index"]["equivalent_rebuild"])
        self.assertEqual(
            revision.evidence_id,
            audit["admission_packages"][0]["evidence_id"],
        )
        published = release.publish(candidate.snapshot_id)
        self.assertEqual("released", published.status)
        self.assertTrue(self.bank.verify_snapshot_content(audit["bank_snapshot_id"]))
        revised_package = accepted_package("release-revision-2")
        revised_package.taxonomy_version_id = release_taxonomy.version_id
        revised_package.proposal.proposal_id = "proposal-revision-2"
        revised_package.proposal.text = "Which place helps you recover after a demanding day?"
        revised_package.evidence.proposal_id = revised_package.proposal.proposal_id
        revised_package.evidence.evidence_id = "evidence-revision-2"
        revised_package.evidence.resolved_facets["semantic_scenario"] = "recovering in a calming place"
        revised_package.evidence.resolved_facets["answer_space"] = "a calming place"
        revised_package.outcome.proposal_id = revised_package.proposal.proposal_id
        revised_package.outcome.outcome_id = "outcome-revision-2"
        revised_package.outcome.evidence_id = revised_package.evidence.evidence_id
        revised_package.theme_classification.proposal_id = revised_package.proposal.proposal_id
        revised_package.theme_classification.classification_id = "themes-revision-2"
        second_revision = self.bank.revise(revision.question_id, revised_package)
        second_candidate = release.build_candidate(
            ReleaseIntent(
                "release-2",
                [second_revision.revision_id],
                release_taxonomy.version_id,
                plan.plan_id,
                policies,
                False,
            )
        )
        self.assertTrue(release.verify(second_candidate.snapshot_id).passed)
        release.publish(second_candidate.snapshot_id)
        rolled_back = release.rollback(candidate.snapshot_id)
        self.assertEqual(candidate.snapshot_id, rolled_back.snapshot_id)
        rolled_revisions = self.bank.list_revisions(audit["bank_snapshot_id"])
        self.assertEqual("active", rolled_revisions[0].lifecycle)
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
                release_taxonomy.version_id,
                plan.plan_id,
                policies,
                True,
            )
        )
        unsafe_report = release.verify(unsafe_candidate.snapshot_id)
        self.assertFalse(unsafe_report.gate_results["semantic_facet_distinctness"])
        withdrawn = release.withdraw(candidate.snapshot_id, "source rights revoked")
        self.assertEqual("withdrawn", withdrawn.status)
        self.assertEqual(second_candidate.snapshot_id, release.current_snapshot_id())
        with self.assertRaisesRegex(ValueError, "withdrawn"):
            release.rollback(candidate.snapshot_id)
        with self.assertRaisesRegex(ValueError, "withdrawn"):
            release.publish(candidate.snapshot_id)
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
