"""LLM-powered helpers used throughout the game flow."""

from __future__ import annotations

from typing import List, Optional

from models import DEFAULT_THEMES, Level
from services.llm_loader import get_llm
from services import llm_prompts


class LLMService:
    """High-level helper that orchestrates all LLM calls."""

    def __init__(self, llm_name: str = "gemini-2.5-flash") -> None:
        self._llm = get_llm(model_name=llm_name)

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
        raw = self._llm.parse_structured(messages, llm_prompts.QuestionLLMResponse)
        # Light refinement pass to improve fluency and simplicity in the chosen language

        try:
            refine_messages = [
                {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": llm_prompts.build_question_refine_prompt(
                        question=raw.question,
                        language=language,
                    ),
                },
            ]
            refined = self._llm.parse_structured(refine_messages, llm_prompts.QuestionLLMResponse)
            if refined and refined.question:
                raw.question = refined.question
        except Exception:
            # If refinement fails for any reason, fall back to the original question.
            pass
        return raw

    def suggest_answer(
        self,
        question: str,
        storyteller_name: str,
        gameplay_mode: str,
        *,
        language: str = "en",
        theme: str = "",
    ) -> llm_prompts.AnswerSuggestionResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_answer_prompt(
                    question,
                    storyteller_name=storyteller_name,
                    gameplay_mode=gameplay_mode,
                    language=language,
                    theme=theme,
                ),
            },
        ]
        try:
            response = self._llm.parse_structured(messages, llm_prompts.AnswerSuggestionResponse)
            if response and response.answer and response.answer.strip():
                return response
        except Exception:
            pass

        fallback_text = self._llm.complete_text(messages).strip()
        return llm_prompts.AnswerSuggestionResponse(answer=fallback_text)

    def build_multiple_choice(
        self,
        question: str,
        true_answer: str,
        level: Level,
        trap_answer: Optional[str] = None,
        num_distractors: int = 2,
        language: str = "en",
        theme: str = "",
    ) -> llm_prompts.MultipleChoiceResponse:
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_multiple_choice_prompt(
                    question=question,
                    true_answer=true_answer,
                    trap_answer=trap_answer,
                    level=level.value,
                    num_distractors=num_distractors,
                    language=language,
                    theme=theme,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.MultipleChoiceResponse)

    def refine_option_text(
        self,
        question: str,
        true_answer: str,
        kind: str,
        current_text: str,
        trap_answer: Optional[str] = None,
        language: str = "en",
    ) -> str:
        """Ask the LLM to rewrite a single option text."""
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_option_refine_prompt(
                    question=question,
                    true_answer=true_answer,
                    trap_answer=trap_answer,
                    kind=kind,
                    current_text=current_text,
                    language=language,
                ),
            },
        ]
        text = self._llm.complete_text(messages)
        return text.strip()

    def rephrase_text(
        self,
        kind: str,
        text: str,
        *,
        language: str = "en",
        question: Optional[str] = None,
        theme: Optional[str] = None,
        level: Optional[str] = None,
    ) -> str:
        """Lightly rephrase text while preserving meaning."""
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": llm_prompts.build_rephrase_prompt(
                    kind=kind,
                    text=text,
                    language=language,
                    question=question,
                    theme=theme,
                    level=level,
                ),
            },
        ]
        return self._llm.complete_text(messages).strip()
