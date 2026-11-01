"""Anonymous question events and per-question counters, isolated by environment."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from services.question_bank import load_questions


class QuestionEvents:
    def __init__(self, environment: str | None = None, sqlite_path: Path | None = None) -> None:
        self.environment = environment or os.getenv('WGY_ENV', 'development')
        if self.environment not in ('development', 'production'):
            raise ValueError('WGY_ENV must be development or production')
        self.path = sqlite_path or Path(__file__).resolve().parent / 'question_events_dev.sqlite3'
        self.url = os.getenv('QUESTION_DB_NEO_URL') or os.getenv('QUESTION_STATS_DATABASE_URL', '')
        if self.environment == 'production' and not self.url:
            raise ValueError('QUESTION_DB_NEO_URL is required in production')

    @contextmanager
    def _connection(self):
        if self.environment == 'production':
            import psycopg
            connection = psycopg.connect(self.url)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _create_schema(self, db) -> None:
        timestamp_type = 'TIMESTAMPTZ' if self.environment == 'production' else 'TEXT'
        db.execute(f'''CREATE TABLE IF NOT EXISTS question_events (
            event_id TEXT PRIMARY KEY, question_id TEXT NOT NULL, action TEXT NOT NULL,
            occurred_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('CREATE TABLE IF NOT EXISTS question_catalog (question_id TEXT PRIMARY KEY, question_text TEXT)')
        if self.environment == 'production':
            db.execute('ALTER TABLE question_catalog ADD COLUMN IF NOT EXISTS question_text TEXT')
        else:
            columns = {row[1] for row in db.execute('PRAGMA table_info(question_catalog)')}
            if 'question_text' not in columns:
                db.execute('ALTER TABLE question_catalog ADD COLUMN question_text TEXT')
            view_columns = {row[1] for row in db.execute('PRAGMA table_info(question_counters)')}
            if view_columns and 'question_text' not in view_columns:
                db.execute('DROP VIEW question_counters')
        db.execute('CREATE INDEX IF NOT EXISTS question_events_question_action ON question_events (question_id, action)')
        view_statement = 'CREATE OR REPLACE VIEW' if self.environment == 'production' else 'CREATE VIEW IF NOT EXISTS'
        db.execute(view_statement + ''' question_counters AS
            SELECT q.question_id,
                COUNT(CASE WHEN e.action = 'shown' THEN 1 END) AS shown_count,
                COUNT(CASE WHEN e.action = 'skipped' THEN 1 END) AS skipped_count,
                COUNT(CASE WHEN e.action = 'confirmed' THEN 1 END) AS confirmed_count,
                COUNT(CASE WHEN e.action = 'confirmed_edited' THEN 1 END) AS confirmed_edited_count,
                COUNT(CASE WHEN e.action = 'saved' THEN 1 END) AS saved_count,
                COUNT(CASE WHEN e.action = 'unsaved' THEN 1 END) AS unsaved_count,
                COUNT(CASE WHEN e.action = 'saved_confirmed' THEN 1 END) AS saved_confirmed_count,
                COUNT(CASE WHEN e.action = 'saved_confirmed_edited' THEN 1 END) AS saved_confirmed_edited_count,
                q.question_text
            FROM question_catalog q LEFT JOIN question_events e ON e.question_id = q.question_id
            GROUP BY q.question_id, q.question_text''')

    def initialize(self, questions: tuple[tuple[str, str], ...] | None = None) -> None:
        """Store original bank text for each question, never its display template."""
        if questions is None:
            questions = tuple((question['id'], question['text']) for question in load_questions())
        placeholder = '%s' if self.environment == 'production' else '?'
        with self._connection() as db:
            self._create_schema(db)
            cursor = db.cursor()
            try:
                cursor.executemany(
                    f'INSERT INTO question_catalog (question_id, question_text) VALUES ({placeholder}, {placeholder}) '
                    'ON CONFLICT (question_id) DO UPDATE SET question_text = excluded.question_text',
                    questions,
                )
            finally:
                cursor.close()

    def record(self, event: dict) -> None:
        placeholder = '%s' if self.environment == 'production' else '?'
        with self._connection() as db:
            self._create_schema(db)
            db.execute(
                f'INSERT INTO question_catalog (question_id) VALUES ({placeholder}) ON CONFLICT (question_id) DO NOTHING',
                (event['question_id'],),
            )
            db.execute(
                f'INSERT INTO question_events (event_id, question_id, action) VALUES ({placeholder}, {placeholder}, {placeholder}) ON CONFLICT (event_id) DO NOTHING',
                (event['id'], event['question_id'], event['action']),
            )
