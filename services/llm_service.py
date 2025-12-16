"""LLM-powered helpers used throughout the game flow."""

from __future__ import annotations

from typing import Iterable, List, Optional

from models import DEFAULT_THEMES, GameplayMode, Level, SUPPORTED_LANGUAGES
from services.llm_loader import get_llm
from services import llm_prompts


class LLMService:
    """High-level helper that orchestrates all LLM calls."""

    def __init__(self, llm_name: str = "gemini-2.5-flash") -> None:
        self._llm = get_llm(model_name=llm_name)
        self._translation_cache: dict[tuple[str, str], str] = {}

    @staticmethod
    def _language_name(code: str) -> str:
        return SUPPORTED_LANGUAGES.get((code or "").lower(), code or "English")

    def _translate_prompt(self, prompt: str, language: str) -> str:
        """Translate system/user prompt into the requested language when not English."""
        if not prompt:
            return prompt
        if not language or language.lower().startswith("en"):
            return prompt
        cache_key = (prompt, language)
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        target_name = self._language_name(language)
        messages = [
            {
                "role": "system",
                "content": llm_prompts.TRANSLATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": llm_prompts.build_translation_prompt(target_name, prompt),
            },
        ]
        print("Translate prompt: ", messages)
        try:
            translated = self._llm.complete_text(messages).strip()
            if translated:
                self._translation_cache[cache_key] = translated
                return translated
        except Exception:
            pass
        return prompt

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
        raw_history = []
        for item in previous_questions or []:
            if not item:
                continue
            text = str(item).strip()
            if text:
                raw_history.append(text)

        # Keep the prompt focused: too much history makes the judge overly strict and can collapse generation.
        history = raw_history[-15:]

        rejection_feedback = ""
        last_rejected_question: Optional[str] = None
        max_attempts = 6
        last_error: Optional[Exception] = None
        last_candidate: Optional[llm_prompts.QuestionLLMResponse] = None

        for _ in range(max_attempts):
            try:
                prompt_text = llm_prompts.build_question_prompt(
                    theme,
                    level.value,
                    history,
                    language,
                    rejection_feedback=rejection_feedback,
                    last_question=last_rejected_question,
                )
                prompt_text = self._translate_prompt(prompt_text, language)
                print(prompt_text)
                messages = [
                    {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": prompt_text,
                    },
                ]
                candidate = self._llm.parse_structured(messages, llm_prompts.QuestionLLMResponse)
            except Exception as exc:
                last_error = exc
                continue

            last_candidate = candidate

            review_accepted = True
            review: Optional[llm_prompts.QuestionReviewResponse] = None
            if len(history) >= 3:
                try:
                    review_prompt = llm_prompts.build_question_review_prompt(
                        question=candidate.question,
                        theme=theme,
                        level=level.value,
                        previous_questions=history,
                        language=language,
                    )
                    review_prompt = self._translate_prompt(review_prompt, language)
                    print(review_prompt)
                    review_messages = [
                        {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": review_prompt,
                        },
                    ]
                    review = self._llm.parse_structured(review_messages, llm_prompts.QuestionReviewResponse)
                    review_accepted = (review.verdict or "").strip().lower() == "accept"
                    print(review)
                except Exception as exc:
                    last_error = exc
                    review_accepted = True  # fail open: don't block the game on judge parsing issues

            if review_accepted:
                try:
                    refine_prompt = llm_prompts.build_question_refine_prompt(
                        question=candidate.question,
                        language=language,
                    )
                    # refine_prompt = self._maybe_translate_prompt(refine_prompt, language)
                    refine_messages = [
                        {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": refine_prompt,
                        },
                    ]
                    refined = self._llm.parse_structured(refine_messages, llm_prompts.QuestionLLMResponse)
                    if refined and refined.question:
                        candidate.question = refined.question
                except Exception:
                    pass
                return candidate

            last_rejected_question = candidate.question
            reason = (review.reason or "").strip() if review else ""
            feedback = (review.feedback or "").strip() if review else ""
            parts: List[str] = []
            if reason:
                parts.append(f"Reason: {reason}")
            if feedback:
                parts.append(f"Regeneration brief:\n{feedback}")
            rejection_feedback = (
                "\n".join(parts).strip() or "Make a bold pivot: choose a clearly different angle and format."
            )

        # If we reach here, prefer returning the best-effort candidate rather than blocking the game.
        if last_candidate:
            try:
                refine_prompt = llm_prompts.build_question_refine_prompt(
                    question=last_candidate.question,
                    language=language,
                )
                # refine_prompt = self._maybe_translate_prompt(refine_prompt, language)
                refine_messages = [
                    {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": refine_prompt,
                    },
                ]
                refined = self._llm.parse_structured(refine_messages, llm_prompts.QuestionLLMResponse)
                if refined and refined.question:
                    last_candidate.question = refined.question
            except Exception:
                pass
            return last_candidate

        if last_error:
            raise RuntimeError(f"Unable to generate question: {last_error}") from last_error
        raise RuntimeError("Unable to generate question after several attempts.")

    def suggest_true_answer(
        self,
        question: str,
        storyteller_name: str,
        gameplay_mode: GameplayMode,
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
                    gameplay_mode=gameplay_mode.value,
                    language=language,
                    theme=theme,
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
        theme: str = "",
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
                    theme=theme,
                ),
            },
        ]
        return self._llm.parse_structured(messages, llm_prompts.AnswerSuggestionResponse)

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
