from __future__ import annotations

import unittest

from question_bank.semantic import PairMetrics, route_pair


class SemanticRoutingTests(unittest.TestCase):
    def test_normalized_exact_is_always_rejected(self) -> None:
        metrics = PairMetrics(0, 0, 0, 0)
        self.assertEqual(
            "local_reject",
            route_pair(" What helps you reset?! ", "what helps you reset", metrics),
        )

    def test_lexical_threshold_edges_are_inclusive(self) -> None:
        self.assertEqual(
            "local_reject",
            route_pair("left", "right", PairMetrics(.88, .2, .94, .2)),
        )
        self.assertEqual(
            "local_reject",
            route_pair("left", "right", PairMetrics(.2, .95, .92, .2)),
        )

    def test_local_distance_requires_every_bound(self) -> None:
        self.assertEqual(
            "local_distance",
            route_pair("left", "right", PairMetrics(.24, .2, .54, .59)),
        )
        self.assertEqual(
            "gpt_review",
            route_pair("left", "right", PairMetrics(.25, .2, .54, .59)),
        )


if __name__ == "__main__":
    unittest.main()
