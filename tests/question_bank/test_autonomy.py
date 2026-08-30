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
from question_bank.autonomy import AutonomousEnrichmentLoop
from question_bank.contracts import CoverageRegion, CoverageRegionKind, QuestionLevel
from question_bank.core import AdmissionDecider, QuestionBank
from question_bank.modules import (
    CoveragePlanner,
    HumanReview,
    QuestionBankNeighborIndex,
    ReferenceExampleRegistry,
    ReleaseModule,
    TaxonomyRegistry,
)
from question_bank.orchestrator import PipelineOrchestrator
from tests.question_bank.test_agents import ScriptedLLM


class AutonomousLoopTests(unittest.TestCase):
    def test_loop_selects_the_coverage_gap_without_human_gap_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "workflow.sqlite3"
            calls: list[dict[str, Any]] = []
            runner = AgentRunner(workflow, lambda preset: ScriptedLLM(preset, calls))
            bank = QuestionBank(root / "bank.sqlite3")
            review = HumanReview(workflow)
            taxonomy = TaxonomyRegistry(workflow)
            version = taxonomy.install_initial(
                "initial-v1",
                ["self_understanding"],
                ["restoration"],
            )
            coverage = CoveragePlanner(workflow, bank)
            coverage.plan(
                {
                    "version_id": version.version_id,
                    "regions": [
                        CoverageRegion(
                            "identity-deep-restoration",
                            "identity",
                            QuestionLevel.DEEP,
                            "self_understanding",
                            "restoration",
                            CoverageRegionKind.REQUIRED,
                        )
                    ],
                }
            )
            references = ReferenceExampleRegistry(workflow)
            release = ReleaseModule(
                workflow,
                bank,
                taxonomy,
                coverage,
                references,
                lambda revisions, packages, snapshot_id, intent: {
                    "quality_revalidation": True,
                    "whole_bank_relation_revalidation": True,
                },
            )
            orchestrator = PipelineOrchestrator(
                workflow,
                ProposalProduction(runner),
                ProposalEvaluation(runner, QuestionBankNeighborIndex(bank), AdmissionDecider()),
                ThemeClassifier(runner),
                bank,
                review,
                ["identity"],
            )
            result = AutonomousEnrichmentLoop(
                taxonomy,
                coverage,
                bank,
                orchestrator,
                review,
                release,
            ).run(
                max_iterations=2,
                concepts_per_scout=1,
                max_proposals=8,
                max_open_reviews=10,
            )
            self.assertEqual(1, len(result["runs"]))
            self.assertEqual([], result["coverage_report"]["gaps"])
            orchestrator.close()
            release.close()
            coverage.close()
            taxonomy.close()
            references.close()
            review.close()
            runner.close()
            bank.close()


if __name__ == "__main__":
    unittest.main()
