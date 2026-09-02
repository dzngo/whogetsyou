from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from question_bank.contracts import (
    ConfigurationManifest,
    ReservedInvocation,
)
from question_bank.providers import (
    NativeGeminiAdapter,
    NativeOpenAIAdapter,
    ProviderFailure,
)


class _Responses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp-one", model="gpt-5.4-mini", output_text=json.dumps({"records": []}),
            usage=SimpleNamespace(
                input_tokens=100,
                input_tokens_details=SimpleNamespace(cached_tokens=20),
                output_tokens=50,
                output_tokens_details=SimpleNamespace(reasoning_tokens=30),
                total_tokens=150,
            ),
        )


class NativeProviderContractTests(unittest.TestCase):
    def test_openai_adapter_uses_one_bounded_responses_call_and_native_usage(self) -> None:
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        role = config.role("quality_medium")
        responses = _Responses()
        adapter = NativeOpenAIAdapter(client=SimpleNamespace(responses=responses))
        invocation = ReservedInvocation("run", "inv", "key", role, {"candidates": []}, "reservation")

        result = adapter.invoke(invocation)

        self.assertEqual(role.output_token_limit, responses.kwargs["max_output_tokens"])
        self.assertEqual({"effort": "medium"}, responses.kwargs["reasoning"])
        self.assertFalse(responses.kwargs["store"])
        schema = responses.kwargs["text"]["format"]["schema"]
        self.assertEqual(
            {
                "candidate_id", "clarity", "answerability", "emotional_safety",
                "level_fit", "deep_revelation", "reason_codes",
            },
            set(schema["properties"]["records"]["items"]["required"]),
        )
        self.assertTrue(role.prompt_hash)
        self.assertTrue(role.schema_hash)
        self.assertTrue(config.reference_fixture_hash)
        self.assertTrue(config.semantic_thresholds_hash)
        self.assertTrue(config.taxonomy_vocabulary_hash)
        self.assertEqual(20, result.usage.cached_input_tokens)
        self.assertEqual(30, result.usage.reasoning_or_thought_tokens)
        self.assertEqual({"records": []}, result.output)

    def test_gemini_adapter_fails_closed_without_total_generated_cap(self) -> None:
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        role = config.creative_roles[0]
        calls = []
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: calls.append(kwargs)))
        adapter = NativeGeminiAdapter(client=fake)
        invocation = ReservedInvocation("run", "inv", "key", role, {}, "reservation")

        with self.assertRaisesRegex(ProviderFailure, "hard_generated_token_cap_unavailable"):
            adapter.invoke(invocation)
        self.assertEqual([], calls)

    def test_explicit_gemini_estimate_exception_sends_one_bounded_high_thinking_call(self) -> None:
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        role = config.creative_roles[0]
        calls = []

        def generate_content(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                text=json.dumps({"questions": [f"Question {index}?" for index in range(5)]}),
                model_version=role.model,
                response_id="gemini-estimated-one",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=100,
                    cached_content_token_count=None,
                    candidates_token_count=50,
                    thoughts_token_count=100,
                    total_token_count=250,
                ),
            )

        adapter = NativeGeminiAdapter(
            client=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content)
            ),
            allow_estimated_total_generated_cap=True,
        )
        invocation = ReservedInvocation("run", "inv", "key", role, {}, "reservation")

        result = adapter.invoke(invocation)

        self.assertEqual(1, len(calls))
        self.assertEqual(
            role.total_generated_token_limit,
            calls[0]["config"]["max_output_tokens"],
        )
        self.assertEqual(
            "HIGH", calls[0]["config"]["thinking_config"]["thinking_level"]
        )
        self.assertEqual(100, result.usage.reasoning_or_thought_tokens)


if __name__ == "__main__":
    unittest.main()
