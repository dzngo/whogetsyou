"""Shared persistent ADK runner used by both operator CLIs."""

from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

from question_bank.adk_app.workflow import build_root_workflow


APP_NAME = "question-bank-enrichment"


async def run_command_async(command: str, backend, *, session_root: Path):
    session_root.mkdir(parents=True, exist_ok=True)
    service = SqliteSessionService(str(session_root / "sessions.sqlite3"))
    runner = Runner(
        agent=build_root_workflow(backend), app_name=APP_NAME,
        session_service=service,
    )
    session_id = f"operator-{uuid.uuid4().hex}"
    await service.create_session(
        app_name=APP_NAME, user_id="local-operator", session_id=session_id
    )
    return [
        event async for event in runner.run_async(
            user_id="local-operator", session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text=command)]
            ),
        )
    ]


def run_command(command: str, backend, *, session_root: Path):
    return asyncio.run(run_command_async(command, backend, session_root=session_root))
