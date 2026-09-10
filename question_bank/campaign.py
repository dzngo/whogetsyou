"""Run a complete paid Question Bank campaign through the production ADK graph."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from question_bank.adk_app.backend import ProductionWorkflowBackend
from question_bank.adk_app.runner import run_command
from question_bank.cli import _configuration
from question_bank.contracts import canonical_data
from question_bank.providers import NativeGeminiAdapter, NativeOpenAIAdapter, ProviderRouter
from question_bank.semantic import FastEmbedAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--authorization-usd", required=True)
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--level", choices=("mixed", "shallow", "deep"), default="mixed")
    parser.add_argument("--checksum-from", type=Path)
    args = parser.parse_args()
    if not args.confirm_paid:
        parser.error("--confirm-paid is required")
    if args.target < 20 or args.target % 20:
        parser.error("--target must be a positive multiple of 20")
    load_dotenv(Path.cwd() / ".env")
    if args.checksum_from and not os.environ.get("QUESTION_BANK_EMBEDDING_CHECKSUM"):
        uri = args.checksum_from.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as database:
            row = database.execute(
                "SELECT payload_json FROM configurations ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            parser.error("--checksum-from has no installed configuration")
        os.environ["QUESTION_BANK_EMBEDDING_CHECKSUM"] = json.loads(row[0])[
            "embedding_checksum"
        ]
    configuration = _configuration()
    backend = ProductionWorkflowBackend(
        args.root,
        provider=ProviderRouter(
            openai=NativeOpenAIAdapter(),
            gemini=NativeGeminiAdapter(allow_estimated_total_generated_cap=True),
        ),
        configuration=configuration,
        embedder=FastEmbedAdapter(checksum=configuration.embedding_checksum),
    )
    command = (
        f"generate campaign={args.campaign_id} proposal_target={args.target} "
        f"level={args.level} bank=v2.1 budget_usd={args.authorization_usd}"
    )
    try:
        events = run_command(command, backend, session_root=args.root / ".adk")
        for event in events:
            if event.output is not None:
                print(json.dumps(canonical_data(event.output), sort_keys=True), flush=True)
        status = backend.engine._store.campaign_status(args.campaign_id)
    finally:
        backend.close()
    return 0 if status["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
