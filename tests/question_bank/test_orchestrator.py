import tempfile
import unittest
from pathlib import Path
from typing import Any

from question_bank.agents import (
    AgentRunner,
    ProposalEvaluation,
    ProposalProduction,
    ThemeClassifier,
)
from question_bank.contracts import (
    AdmissionDecision,
    EnrichmentBrief,
    HumanResolution,
    QuestionLevel,
    ReviewRequest,
    record_dict,
)
from question_bank.core import AdmissionDecider, QuestionBank
from question_bank.modules import HumanReview, QuestionBankNeighborIndex
from question_bank.orchestrator import PipelineOrchestrator
from tests.question_bank.test_agents import ScriptedLLM
from tests.question_bank.test_core import accepted_package


class OrchestratorTests(unittest.TestCase):
    def test_run_is_idempotent_and_admits_only_post_theme_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "workflow.sqlite3"
            calls: list[dict[str, Any]] = []
            runner = AgentRunner(workflow, llm_factory=lambda preset: ScriptedLLM(preset, calls))
            bank = QuestionBank(root / "bank.sqlite3")
            review = HumanReview(workflow)
            snapshot = bank.snapshot({"revision_ids": []})
            orchestrator = PipelineOrchestrator(
                workflow,
                ProposalProduction(runner),
                ProposalEvaluation(runner, QuestionBankNeighborIndex(bank), AdmissionDecider()),
                ThemeClassifier(runner),
                bank,
                review,
                ["identity", "wellbeing"],
                lambda version_id: {
                    "version_id": version_id,
                    "aspects": [{"id": "self_understanding"}],
                    "perspectives": [{"id": "restoration"}],
                },
            )
            brief = EnrichmentBrief(
                "brief-1", "run-key-1", QuestionLevel.DEEP,
                {"region_id": "r1", "aspect_id": "self_understanding", "perspective_id": "restoration"},
                "taxonomy-v1", snapshot.snapshot_id, 1,
            )
            first = orchestrator.run_enrichment(brief)
            call_count = len(calls)
            second = orchestrator.run_enrichment(brief)
            self.assertEqual(first, second)
            self.assertEqual(call_count, len(calls))
            self.assertEqual(4, len(first.accepted_revision_ids))
            self.assertEqual([], review.list_open())
            orchestrator.close()
            review.close()
            runner.close()
            bank.close()

    def test_human_accept_resumes_theme_classification_and_admission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "workflow.sqlite3"
            calls: list[dict[str, Any]] = []
            runner = AgentRunner(workflow, llm_factory=lambda preset: ScriptedLLM(preset, calls))
            bank = QuestionBank(root / "bank.sqlite3")
            review = HumanReview(workflow)
            snapshot = bank.snapshot({"revision_ids": []})
            orchestrator = PipelineOrchestrator(
                workflow,
                ProposalProduction(runner),
                ProposalEvaluation(runner, QuestionBankNeighborIndex(bank), AdmissionDecider()),
                ThemeClassifier(runner),
                bank,
                review,
                ["identity"],
                lambda version_id: {
                    "version_id": version_id,
                    "aspects": [{"id": "self_understanding"}],
                    "perspectives": [{"id": "restoration"}],
                },
            )
            package = accepted_package()
            package.outcome.decision = AdmissionDecision.HUMAN_REVIEW
            case = review.open_case(
                ReviewRequest(
                    "request-human-1",
                    "review-human-1",
                    "admission",
                    package.proposal.proposal_id,
                    {
                        "proposal": record_dict(package.proposal),
                        "evidence": record_dict(package.evidence),
                        "outcome": record_dict(package.outcome),
                        "taxonomy_version_id": "taxonomy-v1",
                        "snapshot_id": snapshot.snapshot_id,
                    },
                )
            )
            result = orchestrator.resolve_review(
                case.case_id,
                HumanResolution("human-resolution-1", "accept", ["human_confirmed"]),
            )
            self.assertEqual("admitted", result["status"])
            self.assertEqual(1, len(bank.list_revisions()))
            orchestrator.close()
            review.close()
            runner.close()
            bank.close()


if __name__ == "__main__":
    unittest.main()
