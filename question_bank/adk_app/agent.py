"""ADK Web entry point for the production Question Bank workflow."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from question_bank.adk_app.backend import ProductionWorkflowBackend
from question_bank.adk_app.workflow import build_web_root_agent
from question_bank.cli import _configuration
from question_bank.providers import NativeGeminiAdapter, NativeOpenAIAdapter, ProviderRouter
from question_bank.semantic import FastEmbedAdapter


load_dotenv(Path.cwd() / ".env")
_root = Path(os.environ.get("QUESTION_BANK_ROOT", "storage/question_bank_v2.1"))
_configuration_manifest = _configuration()
backend = ProductionWorkflowBackend(
    _root,
    provider=ProviderRouter(
        openai=NativeOpenAIAdapter(),
        gemini=NativeGeminiAdapter(allow_estimated_total_generated_cap=True),
    ),
    configuration=_configuration_manifest,
    embedder=FastEmbedAdapter(checksum=_configuration_manifest.embedding_checksum),
)
root_agent = build_web_root_agent(backend)
