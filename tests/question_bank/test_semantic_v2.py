from __future__ import annotations

import unittest

from question_bank.semantic import PairMetrics, route_pair, select_review_pairs


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
            route_pair("left", "right", PairMetrics(.24, .2, .54, .69)),
        )
        self.assertEqual(
            "gpt_review",
            route_pair("left", "right", PairMetrics(.24, .2, .54, .70)),
        )
        self.assertEqual(
            "local_distance",
            route_pair("left", "right", PairMetrics(.25, .2, .54, .69)),
        )
        self.assertEqual(
            "gpt_review",
            route_pair("left", "right", PairMetrics(.251, .2, .54, .69)),
        )

    def test_review_selection_keeps_strongest_neighbor_and_lexical_alerts(self) -> None:
        pairs = [
            {
                "pair_id": "low",
                "candidate_id": "candidate-a",
                "embedding_cosine": .71,
                "token_jaccard": .2,
                "token_containment": .3,
                "character_cosine": .3,
            },
            {
                "pair_id": "strongest",
                "candidate_id": "candidate-a",
                "embedding_cosine": .82,
                "token_jaccard": .2,
                "token_containment": .3,
                "character_cosine": .4,
            },
            {
                "pair_id": "lexical-alert",
                "candidate_id": "candidate-a",
                "embedding_cosine": .72,
                "token_jaccard": .45,
                "token_containment": .5,
                "character_cosine": .66,
            },
            {
                "pair_id": "other-candidate",
                "candidate_id": "candidate-b",
                "embedding_cosine": .73,
                "token_jaccard": .1,
                "token_containment": .2,
                "character_cosine": .2,
            },
        ]

        selected = select_review_pairs(pairs)

        self.assertEqual(
            ["strongest", "lexical-alert", "other-candidate"],
            [pair["pair_id"] for pair in selected],
        )


if __name__ == "__main__":
    unittest.main()
