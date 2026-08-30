import unittest
from unittest.mock import patch

from services.llm_loader import GeminiLLM, OpenAILLM, get_llm


class ProviderRoutingTests(unittest.TestCase):
    @patch("services.llm_loader._get_secret", return_value="test-only-key")
    @patch("services.llm_loader.OpenAI")
    def test_gemini_high_preset_resolves_provider_model_and_thinking(self, _client, _secret) -> None:
        llm = get_llm("gemini-3.5-flash-high")
        self.assertIsInstance(llm, GeminiLLM)
        self.assertEqual("gemini-3.5-flash", llm.model_name)
        self.assertEqual("high", llm._reasoning_effort)

    @patch("services.llm_loader._get_secret", return_value="test-only-key")
    @patch("services.llm_loader.OpenAI")
    def test_gpt_judge_preset_resolves_provider_model_and_reasoning(self, _client, _secret) -> None:
        llm = get_llm("gpt-5.4-mini-high")
        self.assertIsInstance(llm, OpenAILLM)
        self.assertEqual("gpt-5.4-mini", llm.model_name)
        self.assertEqual("high", llm._reasoning_effort)


if __name__ == "__main__":
    unittest.main()
