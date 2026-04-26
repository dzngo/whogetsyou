"""Prompt templates and structured response models for Who Gets You?."""

from __future__ import annotations

import random
from typing import Iterable

from pydantic import BaseModel, Field

from models import SUPPORTED_LANGUAGES, THEME_DESCRIPTIONS

GAME_RULES_SUMMARY = """
"Who Gets You?" is a multiplayer storytelling party game about how well friends understand one another.

- The goal: tell a true, first-person mini-story, then see who can spot the truth.
- Themes are life areas (e.g., childhood, travel, work). Levels are depth: Shallow or Deep.
- The vibe: warm, playful, and specific.

Each round:
1. A Storyteller is chosen and picks the theme and level.
2. The AI proposes one open-ended, emotionally safe question; the Storyteller may regenerate or lightly edit it.
3. Every player submits one answer to the same question.
4. Listeners see all submitted answers and guess which one belongs to the Storyteller.
5. Answers are revealed and points are awarded.

Tone rules for you (the AI):
- Keep questions inclusive, open-ended, and non-triggering (never yes/no or cruel).
- Keep it party-game friendly: funny is welcome, but never humiliating; playful is welcome, but never mean.
- Suggested answers must sound human, specific, conversational, and emotionally safe.
"""

LEVEL_DESCRIPTIONS = {
    "shallow": "Light, ice-breaker territory. Situational facts or quick reflections that anyone can answer without over-sharing.",
    "deep": "Introspective and emotionally aware. Invites vulnerability, formative memories, or personal growth moments while staying respectful.",
}

DEEP_VARIETY_FRAMES = [
    "Spotlight a small turning point—the moment a path or belief changed—and ask what led to it.",
    "Ask for the 'last time' they felt a specific emotion or vibe to ground responses in recent, concrete details.",
    "Frame it as advice to a past or future self so the answer mixes hindsight with vulnerability.",
    "Prompt them to offer advice to someone else facing the same situation, revealing their personal playbook.",
    "Ask them to take a stance—what's their perspective or opinion on a nuanced part of the theme, and why?",
    "Invite them to act as a mini expert—what's an unpopular or under-shared opinion they hold about the theme, and what experiences shaped it?",
    "Use a 'what if' scenario: change one detail about the theme and ask how life might look different.",
    "Ask about a part of their story they've rarely shared—what kept it hidden and why might it matter now?",
    "Invite them to uncover a belief they once held quietly or secretly; what softened or strengthened it?",
    "Explore a regret or near-miss that still tugs at them—what does it reveal about who they hoped to be?",
    "Ask them to revisit a promise they couldn't keep and what that unfinished thread teaches them now.",
    "Ask about their role related to the theme: who they become and how they tend to show up when this part of life is at stake.",
]

SYSTEM_PROMPT = f"""You are the narrative director for the party game "Who Gets You?". \
Use the rules below to keep questions and answers safe, inclusive, and emotionally intelligent.
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


def _pick_theme_focus(theme: str) -> str:
    options = THEME_DESCRIPTIONS.get(theme) or []
    if not options:
        return ""
    candidates = [item.strip() for item in options if item and item.strip()]
    if not candidates:
        return ""
    return random.choice(candidates)


def build_question_prompt(theme: str, level: str, previous_questions: Iterable[str], language: str) -> str:
    language_name = _language_name(language)
    focus_hint = _pick_theme_focus(theme)
    level_lower = (level or "").lower()
    if level_lower == "shallow":
        variety_frame_text = "Keep it light and welcoming; make it easy to answer."
    else:
        variety_frame_text = random.choice(DEEP_VARIETY_FRAMES)
    history_guardrail = (
        "Treat the earlier questions below as off-limits source material—do not copy their structure, opening patterns,"
        " or key phrases, and avoid asking about the same specific situations."
        if previous_questions
        else "Still, write something that feels fresh compared to typical conversation starters."
    )
    variety_line = ""
    if random.random() < 0.7:
        variety_line = f"Variety cue: {variety_frame_text}\n"
    focus_line = f"Optional focus cue (pick one angle only): {focus_hint}\n" if focus_hint else ""
    return (
        f"Generate a single question for the theme '{theme}'.\n"
        f"Depth: {level.title()} — {LEVEL_DESCRIPTIONS.get(level, 'Keep it warm and sincere')}.\n"
        f"{focus_line}"
        f"{_render_previous_questions(previous_questions)}\n"
        f"{history_guardrail}\n"
        f"{variety_line}"
        f"Write the final question entirely in {language_name}.\n"
        "Requirements:\n"
        "- Be creative.\n"
        "- Focus on one specific angle, not a checklist of multiple theme facets.\n"
        "- Keep the question short and clean; avoid long compound wording.\n"
        "- Make it open-ended and non-repetitive.\n"
        "- Do not reuse the same opening pattern across questions.\n"
        "- Avoid asking the same kind of moment/event as prior questions.\n"
        "- Keep it respectful and supportive; avoid cliches, yes/no questions, or harmful framing.\n"
        "- Output JSON with 'question'."
    )


def build_question_refine_prompt(question: str, language: str) -> str:
    language_name = _language_name(language)
    return (
        f"Rewrite the following question so that it becomes clearer and more natural in {language_name}, "
        "and easy for players to answer.\n"
        "Keep the original meaning, but improve the phrasing so it sounds warm and conversational.\n"
        "If the question feels too long, formal, or awkward, make it shorter and smoother while staying respectful.\n"
        f"Question:\n{question}\n"
        "Return JSON with a single field 'question' containing the refined question text."
    )


def build_answer_prompt(question: str, storyteller_name: str, language: str, theme: str = "") -> str:
    language_name = _language_name(language)
    theme_options = THEME_DESCRIPTIONS.get(theme) or []
    theme_note = random.choice(theme_options) if theme_options else ""
    theme_line = f"Theme guidance: {theme_note}\n" if theme_note else ""
    return (
        f"The player is {storyteller_name}. Help them respond to:\n"
        f"Question: {question}\n"
        f"{theme_line}"
        f"Return the answer entirely in {language_name}.\n"
        "Keep it concise, first-person, specific, and natural.\n"
        "Do not include labels, explanations, or markdown.\n"
        "Return JSON with only 'answer'."
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
        f"Rewrite it in {language_name} so it keeps the same meaning but sounds clearer and more natural.\n"
        "Keep the length similar, avoid adding new facts, and keep first-person perspective if present.\n"
        "Return only the rewritten text with no introductions or explanations."
    )


class QuestionLLMResponse(BaseModel):
    question: str = Field(..., description="The final question text delivered to the storyteller.")


class AnswerSuggestionResponse(BaseModel):
    answer: str = Field(..., description="Single first-person answer.")
