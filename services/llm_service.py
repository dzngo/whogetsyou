"""LLM-powered helpers used throughout the game flow."""

from __future__ import annotations

from typing import Iterable, List, Optional

from models import DEFAULT_THEMES, GameplayMode, Level
from services.llm_loader import BaseLLM, get_llm
from services import llm_prompts


class LLMService:
    """High-level helper that orchestrates all LLM calls."""

    def __init__(self, llm: Optional[BaseLLM] = None) -> None:
        self._llm = llm or get_llm()

    def suggest_themes(self) -> List[str]:
        """Returns a list of starter themes."""
        return DEFAULT_THEMES.copy()

    def generate_question(
        self,
        theme: str,
        level: Level,
        previous_questions: Optional[Iterable[str]] = None,
        *,
        language: str = "en",
    ) -> llm_prompts.QuestionLLMResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_question_prompt(
                    theme,
                    level.value,
                    previous_questions or [],
                    language,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.QuestionLLMResponse)

    def suggest_true_answer(
        self,
        question: str,
        storyteller_name: str,
        gameplay_mode: GameplayMode,
        *,
        language: str = "en",
    ) -> llm_prompts.AnswerSuggestionResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_answer_prompt(
                    question,
                    storyteller_name=storyteller_name,
                    gameplay_mode=gameplay_mode.value,
                    language=language,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.AnswerSuggestionResponse)

    def suggest_trap_answer(
        self,
        question: str,
        true_answer: str,
        storyteller_name: str,
        *,
        language: str = "en",
    ) -> llm_prompts.AnswerSuggestionResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_trap_prompt(
                    question=question,
                    true_answer=true_answer,
                    storyteller_name=storyteller_name,
                    language=language,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.AnswerSuggestionResponse)

    def build_multiple_choice(
        self,
        question: str,
        true_answer: str,
        gameplay_mode: GameplayMode,
        level: Level,
        trap_answer: Optional[str] = None,
        num_distractors: int = 2,
        *,
        language: str = "en",
    ) -> llm_prompts.MultipleChoiceResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_multiple_choice_prompt(
                    question=question,
                    true_answer=true_answer,
                    trap_answer=trap_answer,
                    gameplay_mode=gameplay_mode.value,
                    level=level.value,
                    num_distractors=num_distractors,
                    language=language,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.MultipleChoiceResponse)
