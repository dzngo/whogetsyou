from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from question_bank.cli import _configuration, build_parser, main


class ProductionConfigurationTests(unittest.TestCase):
    def test_large_campaign_and_reprocessing_limits_are_explicit_cli_inputs(self) -> None:
        parser = build_parser()
        production = parser.parse_args(
            [
                "run-production-batch",
                "--batch-index",
                "40",
                "--attempt-limit",
                "500",
                "--uncertainty-review-limit",
                "30",
            ]
        )
        recovery = parser.parse_args(
            [
                "reprocess-candidates",
                "--source-candidate-id",
                "candidate-one",
                "--batch-index",
                "0",
            ]
        )

        self.assertEqual(500, production.attempt_limit)
        self.assertEqual(30, production.uncertainty_review_limit)
        self.assertEqual(["candidate-one"], recovery.source_candidate_id)

    def test_local_distance_is_authoritative(self) -> None:
        with patch.dict(
            "os.environ",
            {"QUESTION_BANK_EMBEDDING_CHECKSUM": "verified-test-checksum"},
        ):
            configuration = _configuration()

        self.assertTrue(configuration.local_distance_authority)
        self.assertEqual("semantic-routing-v5", configuration.policy_versions["semantic"])

    @patch("question_bank.cli.run_command", return_value=[])
    @patch("question_bank.cli._adk_backend")
    def test_production_generation_routes_through_shared_adk_runner(
        self, backend_factory, run_command
    ) -> None:
        backend = MagicMock()
        backend_factory.return_value = backend

        result = main([
            "--root", "storage/test-question-bank",
            "run-production-batch", "--batch-index", "0",
            "--authorization-usd", "0.25", "--idempotency-key", "adk-test",
            "--confirm-paid", "--allow-estimated-gemini-cap",
        ])

        self.assertEqual(0, result)
        command = run_command.call_args.args[0]
        self.assertIn("generate campaign=adk-test", command)
        self.assertIn("proposal_target=20", command)
        backend.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
