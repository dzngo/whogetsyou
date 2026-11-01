"""Read and sample the curated gameplay question bank."""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parent.parent / 'storage' / 'curated_question_bank' / 'questions.json'


def load_questions(path: Path = BANK_PATH) -> list[dict]:
    with path.open(encoding='utf-8') as source:
        data = json.load(source)
    questions = data['questions']
    if not isinstance(questions, list):
        raise ValueError('Invalid question bank')
    return questions


def eligible_questions(questions: list[dict], theme: str, level: str, seen: list[str], confirmed: list[str]) -> list[dict]:
    theme_key = theme.split()[0].lower()
    excluded = set(seen) | set(confirmed)
    return [q for q in questions if q['level'] == level and q['id'] not in excluded
            and (theme_key == 'random' or theme_key in q['themes'])]


def sample_question(questions: list[dict], theme: str, level: str, seen: list[str], confirmed: list[str]) -> dict | None:
    eligible = eligible_questions(questions, theme, level, seen, confirmed)
    return random.choice(eligible) if eligible else None


def choose_listener(players: list, storyteller_id: str | None):
    """Choose a listener, excluding the current Storyteller."""
    listeners = [player for player in players if player.player_id != storyteller_id]
    if not storyteller_id or not listeners:
        raise ValueError('A Storyteller and at least one Listener are required for this question.')
    return random.choice(listeners)


def prepare_saved_question(item: dict, players: list, storyteller_id: str | None) -> dict:
    """Update role-based names for the new Storyteller while preserving edits."""
    question = dict(item, source='saved')
    storyteller = next((player for player in players if player.player_id == storyteller_id), None)
    previous_storyteller = item.get('placeholder_storyteller_name')
    replacements = {}
    if previous_storyteller:
        if not storyteller:
            raise ValueError('The current Storyteller could not be found.')
        replacements[previous_storyteller] = storyteller.name
        question['placeholder_storyteller_name'] = storyteller.name

    player_id = item.get('placeholder_player_id')
    eligible_ids = {player.player_id for player in players if player.player_id != storyteller_id}
    if player_id and player_id not in eligible_ids:
        previous_name = item.get('placeholder_player_name', '')
        if not previous_name:
            raise ValueError('The saved question is missing its Listener name.')
        listener = choose_listener(players, storyteller_id)
        replacements[previous_name] = listener.name
        question['placeholder_player_id'] = listener.player_id
        question['placeholder_player_name'] = listener.name

    if replacements:
        # Replace both roles in one pass, so swapping two names cannot cascade.
        names = sorted(replacements, key=len, reverse=True)
        pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(name) for name in names) + r')(?!\w)')
        for key in ('question', 'question_en'):
            question[key] = pattern.sub(lambda match: replacements[match.group()], question.get(key, ''))
    return question


def order_themes_by_distribution(themes: list[str], questions: list[dict]) -> list[str]:
    """Show Random first, then named themes by descending bank membership."""
    counts = Counter(theme for question in questions for theme in set(question['themes']))
    return sorted(themes, key=lambda theme: (
        theme.split()[0].lower() != 'random',
        -counts[theme.split()[0].lower()],
    ))
