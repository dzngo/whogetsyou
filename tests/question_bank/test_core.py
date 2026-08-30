import tempfile
import unittest
from pathlib import Path

from question_bank.contracts import (
    AcceptedQuestionPackage,
    AdmissionDecision,
    AdmissionOutcome,
    EvaluationEvidence,
    QuestionLevel,
    QuestionProposal,
    ThemeClassification,
)
from question_bank.core import AdmissionDecider, QuestionBank


def accepted_package(idempotency_key: str = "admit-1") -> AcceptedQuestionPackage:
    proposal = QuestionProposal(
        proposal_id="proposal-1",
        version=1,
        idempotency_key="proposal-key-1",
        text="What small ritual helps you feel like yourself again?",
        level=QuestionLevel.DEEP,
        aspect_id="self_understanding",
        perspective_id="restoration",
        semantic_scenario="returning to oneself after a difficult day",
        answer_space="a personally meaningful repeatable ritual",
        wording_pattern="open what-question",
        source_permission="de_novo",
        provenance={"concept_id": "concept-1", "composer_invocation_id": "inv-1"},
    )
    evidence = EvaluationEvidence(
        evidence_id="evidence-1",
        proposal_id=proposal.proposal_id,
        complete=True,
        hard_gate_failures=[],
        uncertainties=[],
        semantic_repeat=False,
        judge_invocation_ids=["judge-1", "judge-2", "judge-3", "judge-4", "challenge-1"],
        resolved_facets={
            "aspect_id": proposal.aspect_id,
            "perspective_id": proposal.perspective_id,
            "semantic_scenario": proposal.semantic_scenario,
            "answer_space": proposal.answer_space,
            "wording_pattern": proposal.wording_pattern,
        },
    )
    outcome = AdmissionOutcome(
        outcome_id="outcome-1",
        proposal_id=proposal.proposal_id,
        decision=AdmissionDecision.ACCEPT,
        authority="automatic",
        evidence_id=evidence.evidence_id,
        reason_codes=["all_hard_gates_pass", "globally_distinct"],
    )
    themes = ThemeClassification(
        classification_id="themes-1",
        proposal_id=proposal.proposal_id,
        memberships=["identity", "wellbeing"],
        resolved=True,
        classifier_invocation_ids=["theme-judge", "theme-challenge"],
    )
    return AcceptedQuestionPackage(
        idempotency_key=idempotency_key,
        proposal=proposal,
        evidence=evidence,
        outcome=outcome,
        theme_classification=themes,
        taxonomy_version_id="taxonomy-v1",
        named_theme_ids=["identity", "wellbeing"],
    )


class AdmissionDeciderTests(unittest.TestCase):
    def test_accepts_only_complete_unambiguous_passing_evidence(self) -> None:
        outcome = AdmissionDecider().decide(accepted_package().proposal, accepted_package().evidence)
        self.assertEqual(AdmissionDecision.ACCEPT, outcome.decision)

    def test_fails_closed_to_review_when_evidence_is_missing(self) -> None:
        package = accepted_package()
        package.evidence.complete = False
        outcome = AdmissionDecider().decide(package.proposal, package.evidence)
        self.assertEqual(AdmissionDecision.HUMAN_REVIEW, outcome.decision)
        self.assertIn("missing_evidence", outcome.reason_codes)


class QuestionBankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.bank = QuestionBank(Path(self.tempdir.name) / "bank.sqlite3")

    def tearDown(self) -> None:
        self.bank.close()
        self.tempdir.cleanup()

    def test_admission_is_idempotent_and_creates_immutable_staged_revision(self) -> None:
        package = accepted_package()
        first = self.bank.admit(package)
        second = self.bank.admit(package)
        self.assertEqual(first, second)
        self.assertEqual("staged", first.lifecycle)
        self.assertEqual(1, first.revision_number)
        self.assertEqual(("identity", "wellbeing"), first.theme_memberships)

    def test_rejects_unresolved_theme_classification(self) -> None:
        package = accepted_package()
        package.theme_classification.resolved = False
        with self.assertRaisesRegex(ValueError, "theme classification"):
            self.bank.admit(package)

    def test_revision_preserves_identity_and_snapshot_is_reproducible(self) -> None:
        first = self.bank.admit(accepted_package())
        revised_package = accepted_package("revise-1")
        revised_package.proposal.proposal_id = "proposal-2"
        revised_package.proposal.text = "What habit brings you back to yourself after a hard day?"
        revised_package.evidence.proposal_id = "proposal-2"
        revised_package.outcome.proposal_id = "proposal-2"
        revised_package.theme_classification.proposal_id = "proposal-2"
        second = self.bank.revise(first.question_id, revised_package)
        self.assertEqual(first.question_id, second.question_id)
        self.assertEqual(2, second.revision_number)
        snapshot_a = self.bank.snapshot({"revision_ids": [second.revision_id]})
        snapshot_b = self.bank.snapshot({"revision_ids": [second.revision_id]})
        self.assertEqual(snapshot_a.content_hash, snapshot_b.content_hash)
        with self.assertRaisesRegex(ValueError, "one revision"):
            self.bank.snapshot({"revision_ids": [first.revision_id, second.revision_id]})


if __name__ == "__main__":
    unittest.main()
