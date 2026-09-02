from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from question_bank import (
    CandidateReport,
    CandidateState,
    Level,
    ReferenceFixture,
    UsageSink,
    observed_diversity,
)


class SupportModuleTests(unittest.TestCase):
    def test_frozen_reference_fixture_has_twelve_cases_and_exact_scoring(self) -> None:
        fixture = ReferenceFixture.load_default()
        outcomes = {case["case_id"]: case["expected"] for case in fixture.cases}
        self.assertEqual(12, len(fixture.cases))
        self.assertTrue(fixture.score(outcomes)["passed"])

    def test_usage_sink_is_idempotent_and_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sink = UsageSink(root)
            first = sink.append(idempotency_key="one", question_id="q1", event_type="shown", payload={"room": "x"})
            second = sink.append(idempotency_key="one", question_id="q1", event_type="shown", payload={"room": "x"})
            self.assertEqual(first, second)
            self.assertTrue((root / "question_usage.sqlite3").exists())
            self.assertFalse((root / "question_bank_v2.sqlite3").exists())
            sink.close()

    def test_diversity_feedback_is_bounded_and_advisory(self) -> None:
        candidates = tuple(
            CandidateReport(
                f"c{index}", f"Question {index}?", Level.SHALLOW, "strategy", CandidateState.STAGED,
                theme_memberships=(), metadata={"aspect": "same", "perspective": f"p{index % 4}", "scenario": f"s{index}", "answer_space": f"a{index % 5}", "wording": f"w{index % 4}"},
            )
            for index in range(20)
        )
        report = observed_diversity(candidates)
        self.assertLessEqual(len(report.avoid_patterns), 8)
        self.assertIn("Avoid repeating aspect=same", report.avoid_patterns)
        self.assertTrue(all(candidate.state == CandidateState.STAGED for candidate in candidates))


if __name__ == "__main__":
    unittest.main()
