"""Prompt templates and structured response models for Who Gets You?."""

from __future__ import annotations

import random
from typing import Iterable, Sequence

from pydantic import BaseModel, Field

from models import QuestionAngle, SUPPORTED_LANGUAGES, THEME_DESCRIPTIONS

GAME_RULES_SUMMARY = """
"Who Gets You?" is a multiplayer party game about how well friends understand one another.

- The Guess Target is the Storyteller Answer.
- In Shallow rounds, the Storyteller Answer is what the Storyteller would plausibly prefer, choose, notice, or do in everyday life.
- In Deep rounds, the Storyteller Answer is something personally true about the Storyteller.
- Themes are life areas (e.g., childhood, travel, work), plus Random for surprise.


Tone rules for you (the AI):
- Shallow questions should be realistic, light, quick, and low-stakes. Prefer everyday preferences, habits, routines, tastes, communication styles, small joys, simple choices, and plausible "what if / what would you do" situations.
- Deep questions should be reflective, personal, emotionally safe, and specific.
- Keep generated content inclusive and non-triggering. Shallow can be playful, but avoid cruelty, forced embarrassment, private exposure, discriminatory framing, or sexual pressure.
- Suggested answers must fit the selected level: short and casual for Shallow; first-person, personal, and emotionally safe for Deep.
"""

LEVEL_DESCRIPTIONS = {
    "shallow": "Realistic, low-pressure, and quick. Uses everyday preferences, habits, routines, tastes, simple choices, or plausible situations that do not require serious thinking.",
    "deep": "Introspective and emotionally aware. Invites vulnerability, formative memories, or personal growth moments while staying respectful.",
}

SYSTEM_PROMPT = f"""You are the narrative director for the party game "Who Gets You?". \
Use the rules below to keep questions and answers safe, inclusive, and emotionally intelligent.
{GAME_RULES_SUMMARY.strip()}
Always return JSON that matches the provided schema for the current task."""

TRANSLATION_SYSTEM_PROMPT = (
    "You are a concise translator. Translate only according to the user's instructions. "
    "Preserve meaning, intent, and format. Do not add new ideas, examples, explanations, labels, markdown, or extra questions. "
    "Always return JSON that matches the provided schema for the current task."
)


def _language_name(code: str) -> str:
    return SUPPORTED_LANGUAGES.get((code or "").lower(), code or "English")


def _render_previous_questions(previous_questions: Iterable[str]) -> str:
    cleaned = [q.strip() for q in previous_questions or [] if q and q.strip()]
    if not cleaned:
        return "None provided. Feel free to explore any original angle."
    bullets = "\n".join(f"- {q}" for q in cleaned)
    return f"Previously used questions:\n{bullets}\n"


def _render_selected_angles(selected_angles: Sequence[QuestionAngle]) -> str:
    lines = []
    for angle in selected_angles:
        lines.append(f"- {angle.key}: {angle.guidance}")
    return "\n".join(lines)


def build_candidate_set_prompt(
    *,
    theme: str,
    level: str,
    selected_angles: Sequence[QuestionAngle],
    previous_questions: Iterable[str],
) -> str:
    level_lower = (level or "").lower()
    if level_lower == "shallow":
        level_requirements = (
            "- Make each question realistic, light, quick, and low-pressure.\n"
            "- Ask for one preference, habit, routine, taste, style, choice, small joy, or plausible reaction only.\n"
            "- Direct everyday 'what do you like', 'which do you prefer', and realistic 'what would you do if' shapes are welcome.\n"
            "- Keep situational questions plausible: missed plans, free time, places, errands, meals, weather, messages, breaks, or travel delays.\n"
            "- Do not make premises magical, surreal, childish, object-personified, cartoon-like, cruel, embarrassing, or sexually pressured.\n"
            "- Avoid idioms and compressed phrasing that translate badly, such as 'go-to', 'pick-me-up', 'on a whim', and invented compounds like 'snack-free distraction'.\n"
            "- Prefer plain English that will translate naturally into another language.\n"
            "- Do not ask for a confession, personal growth story, emotional lesson, or deep memory.\n"
        )
    else:
        level_requirements = (
            "- Invite a personally true answer: a value, memory, relationship pattern, belief, regret, hope, or self-understanding.\n"
            "- Keep each question emotionally safe and reflective without becoming heavy, clinical, or therapy-like.\n"
            "- Ask for one specific angle, not a broad life audit.\n"
            "- Prefer concrete, natural wording that will translate well.\n"
        )
    return (
        f"Generate a ranked Candidate Set for the theme '{theme}'.\n"
        f"Depth: {level.title()} — {LEVEL_DESCRIPTIONS.get(level, 'Keep it warm and sincere')}\n"
        "Use the exact Question Angles below. Generate exactly one question for each angle key.\n"
        "Do not invent, rename, merge, skip, or repeat angle keys.\n"
        f"Question Angles:\n{_render_selected_angles(selected_angles)}\n\n"
        f"{_render_previous_questions(previous_questions)}\n"
        "Treat previous questions as off-limits source material. Avoid their structure, opening patterns, key phrases, and broad situations.\n"
        "Rank the candidates from best to weakest for a party game: realistic, natural, easy to answer, theme-connected, diverse, and translation-friendly.\n"
        "Requirements for every candidate:\n"
        "- Write the question entirely in English.\n"
        "- Exactly one sentence and exactly one question mark.\n"
        "- Prefer fewer than 18 words for Shallow; prefer fewer than 24 words for Deep.\n"
        "- Make it easy to answer with a short phrase or sentence.\n"
        "- Do not ask why, ask for examples, or add a reflective tail unless the level is Deep and it is essential.\n"
        "- Do not combine multiple tasks with 'and'.\n"
        "- Avoid yes/no questions, harmful framing, stale wording, and long option lists.\n"
        f"{level_requirements}"
        "Output JSON with a single field 'candidates'. Each item must contain 'rank', 'angle_key', and 'question'."
    )


def build_translation_prompt(text: str, source_language: str, target_language: str) -> str:
    source_name = _language_name(source_language)
    target_name = _language_name(target_language)
    return (
        f"Translate the following text from {source_name} to {target_name}.\n"
        "Rules:\n"
        "- Preserve the original meaning, intent, tone, and format.\n"
        "- Make it natural and playable in the target language.\n"
        "- Preserve whether the text is a question or an answer.\n"
        "- Do not add examples, explanations, labels, markdown, or extra questions.\n"
        "- Return only the translated text in JSON.\n"
        f"Text:\n{text}\n"
        "Return JSON with a single field 'text'."
    )


def build_answer_prompt(
    question: str,
    storyteller_name: str,
    language: str,
    theme: str = "",
    level: str = "",
) -> str:
    del language
    theme_options = THEME_DESCRIPTIONS.get(theme) or []
    theme_note = random.choice(theme_options) if theme_options else ""
    theme_line = f"Theme guidance: {theme_note}\n" if theme_note else ""
    level_lower = (level or "").lower()
    if level_lower == "shallow":
        style_rules = (
            "Make the answer short, casual, realistic, and immediately playable.\n"
            "It should sound like a natural everyday preference, habit, or choice.\n"
            "It does not need to reveal a serious truth or personal story.\n"
        )
    else:
        style_rules = (
            "Keep it concise, first-person, specific, natural, and emotionally safe.\n"
            "It should sound personally true without becoming too heavy.\n"
        )
    return (
        f"The player is {storyteller_name}. Help them respond to:\n"
        f"Question: {question}\n"
        f"{theme_line}"
        "Return the answer entirely in English.\n"
        f"{style_rules}"
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


class QuestionCandidateResponse(BaseModel):
    rank: int = Field(..., description="Ranking position, where 1 is the best candidate.")
    angle_key: str = Field(..., description="Question Angle key used for this candidate.")
    question: str = Field(..., description="Canonical English candidate question.")


class QuestionCandidateSetResponse(BaseModel):
    candidates: list[QuestionCandidateResponse] = Field(..., description="Ranked candidate questions.")


class AnswerSuggestionResponse(BaseModel):
    answer: str = Field(..., description="Single first-person answer.")


class TranslationResponse(BaseModel):
    text: str = Field(..., description="Translated text.")
