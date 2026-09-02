from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from question_bank import (
    CandidateState,
    ConfigurationManifest,
    EnrichmentEngine,
    HashingTestEmbedder,
    HumanReview,
    ProviderResult,
    ProviderUsage,
    RunRequest,
    ScriptedProvider,
)

DIVERSE_QUESTIONS = (
    "Which breakfast detail makes an ordinary morning better?",
    "What kind of message are you quickest to answer?",
    "Which weather makes you want to change your plans?",
    "What do you always notice in a comfortable room?",
    "Which small purchase gives you disproportionate joy?",
    "What makes waiting easier for you?",
    "Which invitation feels impossible to decline?",
    "What do you enjoy organizing more than most people?",
    "Which familiar sound makes you relax?",
    "What kind of detour usually delights you?",
    "Which difficult truth helped you understand yourself?",
    "What makes an apology feel sincere to you?",
    "Which relationship taught you how you want to be seen?",
    "What value do you defend even when it costs you?",
    "Which private hope most shapes your current choices?",
    "What tells you a friendship can survive disagreement?",
    "Which part of yourself took longest to accept?",
    "What do you wish people understood without being told?",
    "Which tradeoff reveals what matters most to you?",
    "What inner change are others least likely to notice?",
)


class OneAmbiguousEmbedder:
    model_id = "one-ambiguous"
    dimensions = 24
    checksum = "one-ambiguous-v1"

    def embed(self, texts):
        vectors = []
        for index, _ in enumerate(texts):
            vector = [0.0] * self.dimensions
            vector[0 if index < 2 else index] = 1.0
            vectors.append(tuple(vector))
        return vectors


class EnrichmentEngineBudgetTests(unittest.TestCase):
    def test_pilot_stops_before_an_unaffordable_creative_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            configuration = ConfigurationManifest.approved_defaults(
                named_themes=("Work", "Love"),
                aspects=("identity", "relationships"),
                perspectives=("preference", "memory"),
            )
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=HashingTestEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="pilot-too-small",
                    snapshot_id=engine.empty_snapshot_id,
                    authorization_usd=Decimal("0.05"),
                )
            )

            self.assertEqual("budget_exhausted", report.stop_reason)
            self.assertEqual((), provider.calls)
            self.assertEqual(Decimal("0.050000"), report.ledger.remaining_usd)
            self.assertEqual(0, report.attempts)
            self.assertEqual((), report.candidates)


class EnrichmentEngineCreativeTests(unittest.TestCase):
    def test_four_isolated_creative_agents_produce_twenty_question_only_candidates(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work", "Love"),
            aspects=("identity", "relationships"),
            perspectives=("preference", "memory"),
            local_distance_authority=True,
        )
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            responses[role.role] = [
                ProviderResult(
                    output={
                        "questions": [
                            f"What reveals part {role_index}-{question_index} of you?"
                            for question_index in range(5)
                        ]
                    },
                    usage=ProviderUsage(1000, 0, 100, 100, 1200),
                    reported_model="gemini-3.5-flash",
                    response_id=f"gemini-{role_index}",
                )
            ]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=HashingTestEmbedder(),
            )
            request = RunRequest.pilot(
                idempotency_key="creative-topology",
                snapshot_id=engine.empty_snapshot_id,
            )

            report = engine.run(request)
            repeated = engine.run(request)

            self.assertEqual("provider_failure", report.stop_reason)
            self.assertEqual(20, len(report.candidates))
            self.assertTrue(
                all(
                    candidate.state == CandidateState.OPERATIONALLY_UNRESOLVED
                    for candidate in report.candidates
                )
            )
            self.assertEqual(10, sum(candidate.level.value == "shallow" for candidate in report.candidates))
            self.assertEqual(10, sum(candidate.level.value == "deep" for candidate in report.candidates))
            creative_calls = provider.calls[:4]
            self.assertEqual(tuple(role.role for role in configuration.creative_roles), tuple(call.role.role for call in creative_calls))
            self.assertTrue(all("theme" not in str(call.payload).lower() for call in creative_calls))
            self.assertTrue(all(len(call.payload["output_schema"]["questions"]) == 5 for call in creative_calls))
            self.assertEqual(5, len(provider.calls))
            self.assertEqual(report, repeated)

    def test_one_malformed_creative_batch_keeps_other_isolated_outputs_durable(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=(), local_distance_authority=True
        )
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            questions = (
                [f"What durable situation {role_index}-{index} reveals you?" for index in range(5)]
                if role_index
                else ["only one"]
            )
            responses[role.role] = [
                ProviderResult(
                    {"questions": questions},
                    ProviderUsage(500, 0, 50, 50, 600),
                    role.model,
                    f"creative-malformed-{role_index}",
                )
            ]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=HashingTestEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="creative-malformed-isolated",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            self.assertEqual("provider_failure", report.stop_reason)
            self.assertEqual(4, len(provider.calls))
            self.assertEqual(15, len(report.candidates))
            self.assertTrue(
                all(
                    item.state == CandidateState.OPERATIONALLY_UNRESOLVED
                    for item in report.candidates
                )
            )

    def test_cross_batch_normalized_duplicate_is_rejected_before_quality(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work",),
            aspects=("identity",),
            perspectives=("memory",),
        )
        responses = {}
        duplicate = "What small ritual helps you reset?"
        for role_index, role in enumerate(configuration.creative_roles):
            questions = [
                f"What distinct situation {role_index}-{index} reveals you?"
                for index in range(5)
            ]
            if role_index == 0:
                questions[0] = duplicate
            if role_index == 3:
                questions[4] = "  what small ritual helps you reset?!  "
            responses[role.role] = [
                ProviderResult(
                    {"questions": questions},
                    ProviderUsage(600, 0, 60, 60, 720),
                    role.model,
                    f"creative-duplicate-{role_index}",
                )
            ]

        def all_quality_pass(invocation):
            records = []
            for candidate in invocation.payload["candidates"]:
                records.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "clarity": "pass",
                        "answerability": "pass",
                        "emotional_safety": "pass",
                        "level_fit": "pass",
                        "deep_revelation": "not_applicable" if candidate["level"] == "shallow" else "pass",
                        "reason_codes": ["passes"],
                    }
                )
            return ProviderResult(
                {"records": records},
                ProviderUsage(2500, 0, 600, 80, 3180),
                "gpt-5.4-mini",
                f"quality-{invocation.invocation_id}",
            )

        responses["quality_medium"] = [all_quality_pass, all_quality_pass]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=HashingTestEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="creative-cross-batch-duplicate",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            duplicates = [
                candidate
                for candidate in report.candidates
                if "normalized_duplicate" in candidate.reason_codes
            ]
            self.assertEqual(1, len(duplicates))
            quality_calls = [call for call in provider.calls if call.role.role == "quality_medium"]
            self.assertEqual(19, sum(len(call.payload["candidates"]) for call in quality_calls))
            self.assertEqual("pair_overflow", report.stop_reason)
            self.assertNotIn("semantic_high", [call.role.role for call in provider.calls])


class EnrichmentEngineQualityTests(unittest.TestCase):
    def test_malformed_quality_batch_never_partially_stages_candidates(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=(), local_distance_authority=True
        )
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            responses[role.role] = [
                ProviderResult(
                    {"questions": DIVERSE_QUESTIONS[role_index * 5 : role_index * 5 + 5]},
                    ProviderUsage(600, 0, 60, 60, 720),
                    role.model,
                    f"malformed-quality-creative-{role_index}",
                )
            ]

        quality_call = 0

        def malformed_second_batch(invocation):
            nonlocal quality_call
            quality_call += 1
            candidates = invocation.payload["candidates"]
            if quality_call == 2:
                candidates = candidates[:-1]
            return ProviderResult(
                {
                    "records": [
                        {
                            "candidate_id": item["candidate_id"],
                            "clarity": "pass",
                            "answerability": "pass",
                            "emotional_safety": "pass",
                            "level_fit": "pass",
                            "deep_revelation": (
                                "not_applicable" if item["level"] == "shallow" else "pass"
                            ),
                            "reason_codes": ["passes"],
                        }
                        for item in candidates
                    ]
                },
                ProviderUsage(2000, 0, 500, 50, 2550),
                "gpt-5.4-mini",
                f"malformed-quality-{quality_call}",
            )

        responses["quality_medium"] = [malformed_second_batch, malformed_second_batch]
        with tempfile.TemporaryDirectory() as directory:
            engine = EnrichmentEngine(
                Path(directory),
                provider=ScriptedProvider(responses),
                configuration=configuration,
                embedder=HashingTestEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="malformed-quality-no-partial-pass",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            self.assertEqual("provider_failure", report.stop_reason)
            self.assertFalse(
                any(item.state == CandidateState.STAGED for item in report.candidates)
            )
            self.assertTrue(
                all(
                    item.state == CandidateState.OPERATIONALLY_UNRESOLVED
                    for item in report.candidates
                )
            )

    def test_two_medium_batches_resolve_definitive_quality_without_high_reasoning(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work", "Love"),
            aspects=("identity", "relationships"),
            perspectives=("preference", "memory"),
            local_distance_authority=True,
        )
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            responses[role.role] = [
                ProviderResult(
                    output={
                        "questions": [
                            DIVERSE_QUESTIONS[role_index * 5 + index]
                            for index in range(5)
                        ]
                    },
                    usage=ProviderUsage(800, 0, 80, 80, 960),
                    reported_model=role.model,
                    response_id=f"creative-{role_index}",
                )
            ]

        def quality_batch(invocation):
            records = []
            for index, candidate in enumerate(invocation.payload["candidates"]):
                verdict = "fail" if index in {0, 5} else "pass"
                records.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "clarity": verdict,
                        "answerability": "pass",
                        "emotional_safety": "pass",
                        "level_fit": "pass",
                        "deep_revelation": (
                            "not_applicable"
                            if candidate["level"] == "shallow"
                            else "pass"
                        ),
                        "reason_codes": ["clear"] if verdict == "pass" else ["unclear"],
                    }
                )
            return ProviderResult(
                output={"records": records},
                usage=ProviderUsage(3000, 0, 800, 100, 3900),
                reported_model="gpt-5.4-mini",
                response_id=f"quality-{invocation.invocation_id}",
            )

        responses["quality_medium"] = [quality_batch, quality_batch]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=OneAmbiguousEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="quality-definitive",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            self.assertEqual("provider_failure", report.stop_reason)
            self.assertEqual(4, sum(candidate.state == CandidateState.REJECTED for candidate in report.candidates))
            self.assertEqual(
                16,
                sum(
                    candidate.state == CandidateState.OPERATIONALLY_UNRESOLVED
                    for candidate in report.candidates
                ),
            )
            roles = [call.role.role for call in provider.calls]
            self.assertEqual(2, roles.count("quality_medium"))
            self.assertNotIn("quality_high", roles)
            self.assertEqual("semantic_high", roles[-1])

    def test_only_uncertain_quality_enters_one_high_reasoning_batch(self) -> None:
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work",),
            aspects=("identity",),
            perspectives=("memory",),
            local_distance_authority=True,
        )
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            responses[role.role] = [
                ProviderResult(
                    output={"questions": [DIVERSE_QUESTIONS[role_index * 5 + index] for index in range(5)]},
                    usage=ProviderUsage(700, 0, 70, 70, 840),
                    reported_model=role.model,
                    response_id=f"creative-uncertain-{role_index}",
                )
            ]
        medium_call = 0

        def quality_medium(invocation):
            nonlocal medium_call
            records = []
            for index, candidate in enumerate(invocation.payload["candidates"]):
                value = "uncertain" if medium_call == 0 and index == 0 else "pass"
                records.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "clarity": value,
                        "answerability": "pass",
                        "emotional_safety": "pass",
                        "level_fit": "pass",
                        "deep_revelation": "not_applicable" if candidate["level"] == "shallow" else "pass",
                        "reason_codes": ["needs_second_read"] if value == "uncertain" else ["passes"],
                    }
                )
            medium_call += 1
            return ProviderResult(
                {"records": records},
                ProviderUsage(2800, 0, 750, 100, 3650),
                "gpt-5.4-mini",
                f"medium-{medium_call}",
            )

        def quality_high(invocation):
            self.assertEqual(1, len(invocation.payload["candidates"]))
            self.assertNotIn("first_verdict", str(invocation.payload).lower())
            candidate = invocation.payload["candidates"][0]
            return ProviderResult(
                {
                    "records": [
                        {
                            "candidate_id": candidate["candidate_id"],
                            "clarity": "pass",
                            "answerability": "pass",
                            "emotional_safety": "pass",
                            "level_fit": "pass",
                            "deep_revelation": "not_applicable" if candidate["level"] == "shallow" else "pass",
                            "reason_codes": ["resolved_pass"],
                        }
                    ]
                },
                ProviderUsage(1000, 0, 500, 150, 1650),
                "gpt-5.4-mini",
                "high-one",
            )

        responses["quality_medium"] = [quality_medium, quality_medium]
        responses["quality_high"] = [quality_high]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=OneAmbiguousEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="quality-uncertainty",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            roles = [call.role.role for call in provider.calls]
            self.assertEqual(1, roles.count("quality_high"))
            self.assertEqual("semantic_high", roles[-1])
            self.assertEqual(20, sum(candidate.state == CandidateState.OPERATIONALLY_UNRESOLVED for candidate in report.candidates))


class EnrichmentEngineSemanticTests(unittest.TestCase):
    def test_one_ambiguous_repeat_is_rejected_and_metadata_failure_keeps_other_questions_staged(self) -> None:
        class ControlledEmbedder:
            model_id = "controlled"
            dimensions = 24
            checksum = "controlled-v1"

            def embed(self, texts):
                vectors = []
                for text in texts:
                    vector = [0.0] * self.dimensions
                    if "hard day" in text or "difficult day" in text:
                        vector[0] = 1.0
                    else:
                        vector[len(vectors) + 1] = 1.0
                    vectors.append(tuple(vector))
                return vectors

        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work", "Love"),
            aspects=("identity", "relationships"),
            perspectives=("preference", "memory"),
            local_distance_authority=True,
        )
        questions = [
            "What helps you recover after a hard day?",
            "Which tiny luxury always improves your morning?",
            "What kind of invitation are you happiest to receive?",
            "Which household task do you secretly enjoy?",
            "What makes a new place feel welcoming to you?",
            "What harmless rule do you almost always ignore?",
            "Which sound instantly changes your mood?",
            "What do you notice first when meeting someone?",
            "Which plan are you most likely to make spontaneously?",
            "What do you protect time for even during a busy week?",
            "After a difficult day, what helps you feel like yourself again?",
            "Which compliment stays with you longest?",
            "What kind of silence feels comfortable to you?",
            "Which promise to yourself matters most right now?",
            "What tells you that you can trust someone?",
            "Which memory changed what courage means to you?",
            "What part of being understood feels rarest to you?",
            "Which tradeoff are you learning to accept?",
            "What private signal tells you that you need support?",
            "Which value becomes clearest when you are under pressure?",
        ]
        responses = {}
        cursor = 0
        for role_index, role in enumerate(configuration.creative_roles):
            responses[role.role] = [
                ProviderResult(
                    {"questions": questions[cursor : cursor + 5]},
                    ProviderUsage(700, 0, 70, 70, 840),
                    role.model,
                    f"creative-semantic-{role_index}",
                )
            ]
            cursor += 5

        def quality_pass(invocation):
            records = [
                {
                    "candidate_id": candidate["candidate_id"],
                    "clarity": "pass",
                    "answerability": "pass",
                    "emotional_safety": "pass",
                    "level_fit": "pass",
                    "deep_revelation": "not_applicable" if candidate["level"] == "shallow" else "pass",
                    "reason_codes": ["passes"],
                }
                for candidate in invocation.payload["candidates"]
            ]
            return ProviderResult(
                {"records": records},
                ProviderUsage(2800, 0, 700, 80, 3580),
                "gpt-5.4-mini",
                f"quality-semantic-{invocation.invocation_id}",
            )

        def semantic_repeat(invocation):
            self.assertLessEqual(len(invocation.payload["pairs"]), 12)
            records = []
            repeat_count = 0
            for pair in invocation.payload["pairs"]:
                is_repeat = (
                    "difficult day" in pair["candidate_text"]
                    and "hard day" in pair["neighbor_text"]
                )
                repeat_count += int(is_repeat)
                records.append(
                    {
                        "pair_id": pair["pair_id"],
                        "scenario": "same" if is_repeat else "different",
                        "perspective": "overlapping" if is_repeat else "different",
                        "answer_space": "same" if is_repeat else "different",
                        "aspect": "overlapping" if is_repeat else "different",
                        "wording": "different",
                        "verdict": "repeat" if is_repeat else "distinct",
                        "reason_codes": [
                            "same_recovery_answer" if is_repeat else "different_meaning"
                        ],
                    }
                )
            self.assertEqual(1, repeat_count)
            return ProviderResult(
                {"pairs": records},
                ProviderUsage(900, 0, 400, 100, 1400),
                "gpt-5.4-mini",
                "semantic-one-repeat",
            )

        responses["quality_medium"] = [quality_pass, quality_pass]
        responses["semantic_high"] = [semantic_repeat]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=ControlledEmbedder(),
            )

            report = engine.run(
                RunRequest.pilot(
                    idempotency_key="semantic-one-repeat",
                    snapshot_id=engine.empty_snapshot_id,
                )
            )

            self.assertEqual("metadata_failed", report.stop_reason)
            self.assertEqual(1, sum("semantic_repeat" in candidate.reason_codes for candidate in report.candidates))
            self.assertEqual(19, sum(candidate.state == CandidateState.STAGED for candidate in report.candidates))
            self.assertEqual("metadata_medium", provider.calls[-1].role.role)


class EnrichmentEngineMetadataTests(unittest.TestCase):
    def test_metadata_enrichment_keeps_admission_and_opens_four_protected_spot_checks(self) -> None:
        class UniqueEmbedder:
            model_id = "unique"
            dimensions = 24
            checksum = "unique-v1"

            def embed(self, texts):
                vectors = []
                for index, _ in enumerate(texts):
                    vector = [0.0] * self.dimensions
                    vector[index] = 1.0
                    vectors.append(tuple(vector))
                return vectors

        configuration = ConfigurationManifest.approved_defaults(
            named_themes=("Work", "Love"),
            aspects=("identity", "relationships"),
            perspectives=("preference", "memory"),
            local_distance_authority=True,
        )
        question_texts = [
            "Which breakfast detail makes an ordinary morning better?",
            "What kind of message are you quickest to answer?",
            "Which weather makes you want to change your plans?",
            "What do you always notice in a comfortable room?",
            "Which small purchase gives you disproportionate joy?",
            "What makes waiting easier for you?",
            "Which invitation feels impossible to decline?",
            "What do you enjoy organizing more than most people?",
            "Which familiar sound makes you relax?",
            "What kind of detour usually delights you?",
            "Which difficult truth helped you understand yourself?",
            "What makes an apology feel sincere to you?",
            "Which relationship taught you how you want to be seen?",
            "What value do you defend even when it costs you?",
            "Which private hope most shapes your current choices?",
            "What tells you a friendship can survive disagreement?",
            "Which part of yourself took longest to accept?",
            "What do you wish people understood without being told?",
            "Which tradeoff reveals what matters most to you?",
            "What inner change are others least likely to notice?",
        ]
        responses = {}
        for role_index, role in enumerate(configuration.creative_roles):
            start = role_index * 5
            responses[role.role] = [
                ProviderResult(
                    {"questions": question_texts[start : start + 5]},
                    ProviderUsage(650, 0, 60, 60, 770),
                    role.model,
                    f"metadata-creative-{role_index}",
                )
            ]

        def pass_quality(invocation):
            return ProviderResult(
                {
                    "records": [
                        {
                            "candidate_id": candidate["candidate_id"],
                            "clarity": "pass",
                            "answerability": "pass",
                            "emotional_safety": "pass",
                            "level_fit": "pass",
                            "deep_revelation": "not_applicable" if candidate["level"] == "shallow" else "pass",
                            "reason_codes": ["passes"],
                        }
                        for candidate in invocation.payload["candidates"]
                    ]
                },
                ProviderUsage(2600, 0, 600, 80, 3280),
                "gpt-5.4-mini",
                f"metadata-quality-{invocation.invocation_id}",
            )

        def distinct_pairs(invocation):
            return ProviderResult(
                {
                    "pairs": [
                        {
                            "pair_id": pair["pair_id"],
                            "scenario": "different",
                            "perspective": "different",
                            "answer_space": "different",
                            "aspect": "different",
                            "wording": "different",
                            "verdict": "distinct",
                            "reason_codes": ["different_meaning"],
                        }
                        for pair in invocation.payload["pairs"]
                    ]
                },
                ProviderUsage(1000, 0, 450, 100, 1550),
                "gpt-5.4-mini",
                "metadata-semantic",
            )

        def metadata(invocation):
            return ProviderResult(
                {
                    "records": [
                        {
                            "candidate_id": question["candidate_id"],
                            "themes": [],
                            "themes_resolved": True,
                            "aspect": "identity",
                            "perspective": "preference",
                            "scenario": f"scenario-{index}",
                            "answer_space": f"answer-{index}",
                            "wording": f"wording-{index}",
                            "uncertain_fields": [],
                        }
                        for index, question in enumerate(invocation.payload["questions"])
                    ]
                },
                ProviderUsage(2800, 0, 700, 80, 3580),
                "gpt-5.4-mini",
                "metadata-complete",
            )

        responses["quality_medium"] = [pass_quality, pass_quality]
        responses["semantic_high"] = [distinct_pairs]
        responses["metadata_medium"] = [metadata]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(
                Path(directory),
                provider=provider,
                configuration=configuration,
                embedder=UniqueEmbedder(),
            )

            request = RunRequest.pilot(
                    idempotency_key="metadata-complete",
                    snapshot_id=engine.empty_snapshot_id,
                )
            report = engine.run(request)

            self.assertEqual("pilot_spot_check", report.stop_reason)
            self.assertEqual("awaiting_human_review", report.status)
            self.assertEqual(20, sum(candidate.state == CandidateState.STAGED for candidate in report.candidates))
            self.assertTrue(all(candidate.theme_memberships == () for candidate in report.candidates))
            self.assertTrue(all(candidate.metadata["aspect"] == "identity" for candidate in report.candidates))
            self.assertEqual(4, len(report.review_case_ids))
            review = HumanReview(Path(directory))
            for index, case_id in enumerate(report.review_case_ids):
                review.resolve(
                    case_id, {"action": "pass", "reason_codes": ["verified"]},
                    idempotency_key=f"spot-pass-{index}",
                )
            review.close()
            completed = engine.run(request)
            self.assertEqual("pilot_passed", completed.stop_reason)
            self.assertEqual("completed", completed.status)


if __name__ == "__main__":
    unittest.main()
