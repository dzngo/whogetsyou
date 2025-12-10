"""Prompt templates and structured response models for Who Gets You?."""

from __future__ import annotations

from typing import Iterable, List

from pydantic import BaseModel, Field
from typing_extensions import Literal

from models import SUPPORTED_LANGUAGES

GAME_RULES_SUMMARY = """
"Who Gets You?" is a multiplayer storytelling game about how well friends understand one another.

- Themes are life areas (e.g., childhood, travel, work). Levels are emotional depth: Shallow, Medium, Deep. Deeper rounds mean more points.

Each round:
1. A Storyteller is chosen and, if needed, picks the theme and level.
2. The AI proposes one open-ended, emotionally safe question; the Storyteller may regenerate or lightly edit it.
3. The Storyteller writes a true, first-person answer. In Bluffing mode they also write one believable but false trap answer.
4. The AI builds multiple-choice options from the true answer, the trap (if any), and a few natural-sounding distractors.
5. Listeners only see the options and guess which one is true; then answers are revealed and points are awarded.

Tone rules for you (the AI):
- Keep questions inclusive, open-ended, and non-triggering (never yes/no or cruel).
- Make all answers (true, trap, distractors) sound like one real person: specific, conversational, and kind.
- Traps should be plausible and close-to-true, not absurd, humiliating, or obviously fake.
"""

LEVEL_DESCRIPTIONS = {
    "shallow": "Light, ice-breaker territory. Situational facts or quick reflections that anyone can answer without over-sharing.",
    "medium": "Thoughtful but comfortable. Encourages short stories or opinions that reveal personality and values.",
    "deep": "Introspective and emotionally aware. Invites vulnerability, formative memories, or personal growth moments while staying respectful.",
}

SYSTEM_PROMPT = f"""You are the narrative director for the party game "Who Gets You?". \
Use the rules below to keep questions, answers, and multiple-choice options safe, inclusive, and emotionally intelligent.
{GAME_RULES_SUMMARY.strip()}
Always return JSON that matches the provided schema for the current task."""


def _language_name(code: str) -> str:
    return SUPPORTED_LANGUAGES.get((code or "").lower(), code or "English")


def _render_previous_questions(previous_questions: Iterable[str]) -> str:
    cleaned = [q.strip() for q in previous_questions or [] if q and q.strip()]
    if not cleaned:
        return "None provided. Feel free to explore any original angle."
    bullets = "\n".join(f"- {q}" for q in cleaned)
    return f"Previously used questions:\n{bullets}"


def build_question_prompt(theme: str, level: str, previous_questions: Iterable[str], language: str) -> str:
    language_name = _language_name(language)
    return (
        f"Generate a single question for the theme '{theme}'.\n"
        f"Depth: {level.title()} — {LEVEL_DESCRIPTIONS.get(level, 'Keep it warm and sincere')}.\n"
        f"{_render_previous_questions(previous_questions)}\n"
        f"Write the final question entirely in {language_name}.\n"
        "Requirements:\n"
        "- Make it open-ended and non-repetitive.\n"
        "- Keep it respectful and supportive; avoid cliches, yes/no questions, or anything that might trigger trauma.\n"
        "- Output JSON with 'question'."
    )


def build_answer_prompt(question: str, storyteller_name: str, gameplay_mode: str, language: str) -> str:
    language_name = _language_name(language)
    honesty_hint = (
        "Simple mode: answer truthfully while sounding conversational and specific."
        if gameplay_mode == "simple"
        else "Bluffing mode: provide the Storyteller's honest answer that still feels vulnerable."
    )
    return (
        f"The storyteller is {storyteller_name}. Help them respond to:\n"
        f"Question: {question}\n"
        f"{honesty_hint}\n"
        f"Return the answer entirely in {language_name}.\n"
        "Avoid to be wordy.\n"
        "Return JSON with 'answer' (first-person) briefly explaining the emotional note you aimed for."
    )


def build_trap_prompt(question: str, true_answer: str, storyteller_name: str, language: str) -> str:
    language_name = _language_name(language)
    return (
        f"The storyteller {storyteller_name} already has the true answer below.\n"
        f"Question: {question}\n"
        f"True answer: {true_answer}\n"
        "Invent a believable but wrong answer (the 'trap') that close friends might mistake for the truth. "
        "Keep tone consistent with the storyteller's voice and avoid contradicting obvious facts from the true answer.\n"
        f"Write the trap entirely in {language_name}.\n"
        "Avoid to be wordy.\n"
        "Return JSON with 'answer'."
    )


def build_multiple_choice_prompt(
    question: str,
    true_answer: str,
    trap_answer: str | None,
    level: str,
    num_distractors: int,
    language: str,
) -> str:
    language_name = _language_name(language)
    trap_line = (
        f"The storyteller also provided a trap answer for Bluffing mode:\nTrap: {trap_answer}\n"
        if trap_answer
        else "Gameplay mode is Simple so there is no trap answer.\n"
    )
    return (
        f"Create multiple-choice options for listeners guessing {question}\n"
        f"Depth guidance: {level.title()} — {LEVEL_DESCRIPTIONS.get(level, 'balanced tone')}.\n"
        f"True answer: {true_answer}\n"
        f"{trap_line}"
        f"Write every option entirely in {language_name}.\n"
        f"Include exactly {num_distractors} additional distractors that sound natural.\n"
        "Avoid to be wordy.\n"
        "Label answers sequentially starting at A. Output JSON with:\n"
        "- options (list of objects with 'label', 'text', 'kind' of 'true'|'trap'|'distractor')\n"
    )


def build_option_refine_prompt(
    question: str,
    true_answer: str,
    trap_answer: str | None,
    kind: str,
    current_text: str,
    language: str,
) -> str:
    language_name = _language_name(language)
    base = (
        f"You are adjusting a single multiple-choice option for the game 'Who Gets You?'.\n"
        f"Question: {question}\n"
        f"True answer: {true_answer}\n"
    )
    if trap_answer:
        base += f"Trap answer (if applicable): {trap_answer}\n"
    kind_explainer = {
        "true": "Rewrite the *true* answer so it stays faithful to the meaning but feels natural, specific, and human.",
        "trap": "Rewrite the *trap* answer so it sounds very believable and close to the truth, but still not exactly correct.",
        "distractor": "Rewrite the *distractor* so it feels plausible and in-character but clearly not the real answer.",
    }.get(kind, "Rewrite this option so it fits the tone and context of the other answers.")
    return (
        base
        + f"Current option text: {current_text or '[empty]'}\n"
        + f"Role of this option: {kind}.\n"
        + f"{kind_explainer}\n"
        + f"Write the new option entirely in {language_name}.\n"
        + "Return only the revised option text, no bullet points or explanations."
    )


def build_rephrase_prompt(
    kind: str,
    text: str,
    language: str,
    question: str | None = None,
    theme: str | None = None,
    level: str | None = None,
) -> str:
    language_name = _language_name(language)
    context = f"Reference question for context:\n{question}\n" if question else ""
    theme_line = f"Theme: {theme}\n" if theme else ""
    level_line = f"Depth level: {level}\n" if level else ""
    return (
        f"You are polishing a {kind} for the game 'Who Gets You?'.\n"
        f"{context}"
        f"{theme_line}"
        f"{level_line}"
        f"Original text:\n{text}\n"
        f"Rewrite it in {language_name} so it keeps the same meaning but sounds clearer, more natural, and emotionally aware.\n"
        "Keep the length similar, avoid adding new facts, and do not change first-person perspective if present.\n"
        "Return only the rewritten text with no introductions or explanations."
    )


class QuestionLLMResponse(BaseModel):
    question: str = Field(..., description="The final question text delivered to the storyteller.")


class AnswerSuggestionResponse(BaseModel):
    answer: str = Field(..., description="Single first-person answer.")


class MultipleChoiceOption(BaseModel):
    label: str = Field(..., description="Single-letter identifier such as A, B, C, ...")
    text: str = Field(..., description="What the listeners read.")
    kind: Literal["true", "trap", "distractor"] = Field(
        ..., description="How this option should be treated in scoring."
    )


class MultipleChoiceResponse(BaseModel):
    options: List[MultipleChoiceOption]
