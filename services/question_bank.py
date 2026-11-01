"""Read and sample the curated gameplay question bank."""
from __future__ import annotations

import json
import os
import random
import re
from collections import Counter
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parent.parent / 'storage' / 'curated_question_bank' / 'questions.json'


def load_local_questions(path: Path = BANK_PATH) -> list[dict]:
    """Read the local curated bank, including when preparing a Neon upload."""
    with path.open(encoding='utf-8') as source:
        data = json.load(source)
    questions = data['questions']
    if not isinstance(questions, list):
        raise ValueError('Invalid question bank')
    return questions


def load_questions() -> list[dict]:
    """Read the production bank from Neon; development uses local JSON."""
    environment = os.getenv('WGY_ENV', 'development')
    if environment == 'development':
        return load_local_questions()
    if environment != 'production':
        raise ValueError('WGY_ENV must be development or production')
    url = os.getenv('QUESTION_DB_NEO_URL') or os.getenv('QUESTION_STATS_DATABASE_URL')
    if not url:
        raise RuntimeError('QUESTION_DB_NEO_URL is required to load production questions')
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(url, connect_timeout=10, row_factory=dict_row) as connection:
            rows = connection.execute(
                'SELECT question_id AS id, question_text AS text, display_template, level, themes, approved_at '
                'FROM question_bank ORDER BY question_id'
            ).fetchall()
        if not rows:
            raise ValueError('The production question bank is empty')
        for row in rows:
            if not isinstance(row['themes'], list) or not all(isinstance(theme, str) for theme in row['themes']):
                raise ValueError('A production question has invalid themes')
            if row['approved_at'] is not None:
                row['approved_at'] = row['approved_at'].isoformat()
        return rows
    except Exception:
        # Database exceptions may include connection details; avoid exposing credentials.
        raise RuntimeError('Unable to load the production question bank from Neon.') from None


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
