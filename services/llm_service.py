"""LLM-powered helpers used throughout the game flow."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional

from models import DEFAULT_THEMES, GENERIC_QUESTION_ANGLES, QUESTION_ANGLES, Level, QuestionAngle
from services.llm_loader import get_llm
from services import llm_prompts


@dataclass
class QuestionGenerationTrace:
    """Question output plus the prompt chain used to produce it."""

    question: str
    question_en: str
    generation_prompt_system: str
    generation_prompt_user: str
    translation_prompt_system: str = ""
    translation_prompt_user: str = ""
    translation_model: str = ""
    translation_error: str = ""
    angle_key: str = ""


@dataclass
class QuestionCandidateTrace:
    """One canonical English candidate from a ranked Candidate Set."""

    rank: int
    angle_key: str
    question_en: str


@dataclass
class QuestionCandidateSetTrace:
    """Ranked Candidate Set plus generation prompt trace."""

    candidates: List[QuestionCandidateTrace]
    selected_angle_keys: List[str]
    generation_prompt_system: str
    generation_prompt_user: str


@dataclass
class AnswerSuggestionTrace:
    """Suggested answer output plus canonical English and translation trace."""

    answer: str
    answer_en: str
    generation_prompt_system: str
    generation_prompt_user: str
    translation_prompt_system: str = ""
    translation_prompt_user: str = ""
    translation_model: str = ""
    translation_error: str = ""


class LLMService:
    """High-level helper that orchestrates all LLM calls."""

    TRANSLATION_MODEL = "gpt-5.4-nano"
    DEFAULT_CANDIDATE_COUNT = 5
    RECENT_ANGLE_EXCLUSION_COUNT = 3

    def __init__(self, llm_name: str = "gemini-2.5-flash") -> None:
        self._llm = get_llm(model_name=llm_name)
        self._translator = None

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
        trace = self.generate_question_with_trace(
            theme=theme,
            level=level,
            previous_questions=previous_questions,
            language=language,
        )
        return llm_prompts.QuestionLLMResponse(question=trace.question)

    def generate_question_with_trace(
        self,
        theme: str,
        level: Level,
        previous_questions: Optional[Iterable[str]] = None,
        *,
        language: str = "en",
    ) -> QuestionGenerationTrace:
        candidate_set = self.generate_question_candidate_set_with_trace(
            theme=theme,
            level=level,
            previous_questions=previous_questions,
            angle_history=[],
            candidate_count=1,
        )
        if not candidate_set.candidates:
            raise RuntimeError("No question candidates were generated")
        top_candidate = candidate_set.candidates[0]
        translation_trace = self.translate_text_with_trace(
            text=top_candidate.question_en,
            source_language="en",
            target_language=language,
        )
        return QuestionGenerationTrace(
            question=translation_trace["text"],
            question_en=top_candidate.question_en,
            generation_prompt_system=candidate_set.generation_prompt_system,
            generation_prompt_user=candidate_set.generation_prompt_user,
            translation_prompt_system=translation_trace["prompt_system"],
            translation_prompt_user=translation_trace["prompt_user"],
            translation_model=translation_trace["model"],
            translation_error=translation_trace["error"],
            angle_key=top_candidate.angle_key,
        )

    def generate_question_candidate_set_with_trace(
        self,
        *,
        theme: str,
        level: Level,
        previous_questions: Optional[Iterable[str]] = None,
        angle_history: Optional[Iterable[str]] = None,
        candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    ) -> QuestionCandidateSetTrace:
        previous = list(previous_questions or [])
        selected_angles = self._select_question_angles(
            theme=theme,
            level=level,
            angle_history=list(angle_history or []),
            count=candidate_count,
        )
        generation_prompt_user = llm_prompts.build_candidate_set_prompt(
            theme=theme,
            level=level.value,
            selected_angles=selected_angles,
            previous_questions=previous,
        )
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": generation_prompt_user},
        ]
        selected_keys = [angle.key for angle in selected_angles]
        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                raw = self._llm.parse_structured(messages, llm_prompts.QuestionCandidateSetResponse)
                candidates = self._validate_candidate_set(raw, selected_keys)
                return QuestionCandidateSetTrace(
                    candidates=candidates,
                    selected_angle_keys=selected_keys,
                    generation_prompt_system=llm_prompts.SYSTEM_PROMPT,
                    generation_prompt_user=generation_prompt_user,
                )
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Invalid question candidate set: {last_error}") from last_error

    def _select_question_angles(
        self,
        *,
        theme: str,
        level: Level,
        angle_history: List[str],
        count: int,
    ) -> List[QuestionAngle]:
        catalog = (QUESTION_ANGLES.get(theme) or {}).get(level.value)
        if not catalog:
            catalog = GENERIC_QUESTION_ANGLES[level.value]
        target_count = max(1, min(count, len(catalog)))
        recent = set(angle_history[-self.RECENT_ANGLE_EXCLUSION_COUNT :])
        available = [angle for angle in catalog if angle.key not in recent]
        if len(available) < target_count:
            available = list(catalog)
        selected: List[QuestionAngle] = []
        pool = list(available)
        while pool and len(selected) < target_count:
            weights = [max(angle.weight, 0.01) for angle in pool]
            choice = random.choices(pool, weights=weights, k=1)[0]
            selected.append(choice)
            pool = [angle for angle in pool if angle.key != choice.key]
        return selected

    def _validate_candidate_set(
        self,
        raw: llm_prompts.QuestionCandidateSetResponse,
        selected_angle_keys: List[str],
    ) -> List[QuestionCandidateTrace]:
        raw_candidates = list(raw.candidates or [])
        if len(raw_candidates) != len(selected_angle_keys):
            raise ValueError("Candidate count does not match selected angles")
        allowed_keys = set(selected_angle_keys)
        seen_keys = set()
        seen_ranks = set()
        normalized: List[QuestionCandidateTrace] = []
        for item in raw_candidates:
            angle_key = (item.angle_key or "").strip()
            question = (item.question or "").strip()
            if angle_key not in allowed_keys:
                raise ValueError(f"Unexpected angle key: {angle_key}")
            if angle_key in seen_keys:
                raise ValueError(f"Duplicate angle key: {angle_key}")
            if item.rank in seen_ranks:
                raise ValueError(f"Duplicate rank: {item.rank}")
            if not question:
                raise ValueError("Candidate question is empty")
            if question.count("?") != 1:
                raise ValueError(f"Candidate question must contain exactly one question mark: {question}")
            seen_keys.add(angle_key)
            seen_ranks.add(item.rank)
            normalized.append(
                QuestionCandidateTrace(
                    rank=item.rank,
                    angle_key=angle_key,
                    question_en=question,
                )
            )
        if seen_keys != allowed_keys:
            raise ValueError("Candidate set is missing selected angle keys")
        normalized.sort(key=lambda candidate: candidate.rank)
        if [candidate.rank for candidate in normalized] != list(range(1, len(normalized) + 1)):
            raise ValueError("Candidate ranks must be contiguous from 1")
        return [
            QuestionCandidateTrace(
                rank=index,
                angle_key=candidate.angle_key,
                question_en=candidate.question_en,
            )
            for index, candidate in enumerate(normalized, start=1)
        ]

    def translate_text(self, text: str, *, source_language: str, target_language: str) -> str:
        return self.translate_text_with_trace(
            text=text,
            source_language=source_language,
            target_language=target_language,
        )["text"]

    def translate_text_with_trace(self, text: str, *, source_language: str, target_language: str) -> dict:
        cleaned = (text or "").strip()
        source = (source_language or "en").lower()
        target = (target_language or "en").lower()
        if not cleaned or source == target:
            return {
                "text": cleaned,
                "prompt_system": "",
                "prompt_user": "",
                "model": "",
                "error": "",
            }
        prompt_user = llm_prompts.build_translation_prompt(
            text=cleaned,
            source_language=source,
            target_language=target,
        )
        messages = [
            {"role": "system", "content": llm_prompts.TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_user},
        ]
        try:
            translated = self._get_translator().parse_structured(messages, llm_prompts.TranslationResponse)
            translated_text = (translated.text or "").strip()
            return {
                "text": translated_text or cleaned,
                "prompt_system": llm_prompts.TRANSLATION_SYSTEM_PROMPT,
                "prompt_user": prompt_user,
                "model": self.TRANSLATION_MODEL,
                "error": "",
            }
        except Exception as exc:
            return {
                "text": cleaned,
                "prompt_system": llm_prompts.TRANSLATION_SYSTEM_PROMPT,
                "prompt_user": prompt_user,
                "model": self.TRANSLATION_MODEL,
                "error": str(exc),
            }

    def _get_translator(self):
        if self._translator is None:
            self._translator = get_llm(model_name=self.TRANSLATION_MODEL)
        return self._translator

    def suggest_answer(
        self,
        question: str,
        storyteller_name: str,
        *,
        language: str = "en",
        theme: str = "",
        level: str = "",
        question_en: str = "",
    ) -> llm_prompts.AnswerSuggestionResponse:
        trace = self.suggest_answer_with_trace(
            question=question,
            storyteller_name=storyteller_name,
            language=language,
            theme=theme,
            level=level,
            question_en=question_en,
        )
        if (language or "en").lower() != "en" and trace.translation_error:
            raise RuntimeError(trace.translation_error)
        return llm_prompts.AnswerSuggestionResponse(answer=trace.answer)

    def suggest_answer_with_trace(
        self,
        question: str,
        storyteller_name: str,
        *,
        language: str = "en",
        theme: str = "",
        level: str = "",
        question_en: str = "",
    ) -> AnswerSuggestionTrace:
        prompt_user = llm_prompts.build_answer_prompt(
            question_en or question,
            storyteller_name=storyteller_name,
            language="en",
            theme=theme,
            level=level,
        )
        messages = [
            {"role": "system", "content": llm_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt_user},
        ]
        try:
            response = self._llm.parse_structured(messages, llm_prompts.AnswerSuggestionResponse)
            if response and response.answer and response.answer.strip():
                answer_en = response.answer.strip()
            else:
                answer_en = ""
        except Exception:
            answer_en = ""
        if not answer_en:
            answer_en = self._llm.complete_text(messages).strip()
        translation_trace = self.translate_text_with_trace(
            text=answer_en,
            source_language="en",
            target_language=language,
        )
        return AnswerSuggestionTrace(
            answer=translation_trace["text"],
            answer_en=answer_en,
            generation_prompt_system=llm_prompts.SYSTEM_PROMPT,
            generation_prompt_user=prompt_user,
            translation_prompt_system=translation_trace["prompt_system"],
            translation_prompt_user=translation_trace["prompt_user"],
            translation_model=translation_trace["model"],
            translation_error=translation_trace["error"],
        )

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
