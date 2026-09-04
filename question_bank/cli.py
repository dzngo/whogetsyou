"""Offline-first operator CLI for Question Bank Enrichment v2."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from models import THEME_DESCRIPTIONS
from question_bank.contracts import ConfigurationManifest, RunRequest, canonical_data
from question_bank.engine import EnrichmentEngine
from question_bank.migration import archive_legacy_storage
from question_bank.providers import (
    NativeGeminiAdapter,
    NativeOpenAIAdapter,
    ProviderRouter,
)
from question_bank.regression import ReferenceFixture
from question_bank.release import ReleaseModule
from question_bank.review import HumanReview
from question_bank.semantic import FastEmbedAdapter
from question_bank.store import V2Store

DEFAULT_ASPECTS = (
    "everyday_habits_and_preferences", "growth_work_and_aspiration",
    "identity_and_inner_life", "origins_and_formative_experiences",
    "play_places_and_exploration", "relationships_and_belonging",
)
DEFAULT_PERSPECTIVES = (
    "aspiration_and_tradeoff", "habitual_reaction", "memory_and_influence",
    "preference_and_aversion", "social_role_and_connection", "values_and_self_perception",
)


def _configuration() -> ConfigurationManifest:
    checksum = os.environ.get("QUESTION_BANK_EMBEDDING_CHECKSUM", "test-or-install-time-checksum")
    themes = tuple(sorted(theme for theme in THEME_DESCRIPTIONS if "Random" not in theme))
    return ConfigurationManifest.approved_defaults(
        named_themes=themes, aspects=DEFAULT_ASPECTS, perspectives=DEFAULT_PERSPECTIVES,
        embedding_checksum=checksum,
        embedding_runtime_version=f"fastembed-{_package_version('fastembed')}",
        local_distance_authority=True,
    )


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _print(value) -> None:
    print(json.dumps(canonical_data(value), indent=2, sort_keys=True))


def _release(root: Path) -> ReleaseModule:
    config = _configuration()
    return ReleaseModule(
        root, configuration=config,
        embedder=FastEmbedAdapter(checksum=config.embedding_checksum),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="question-bank")
    parser.add_argument("--root", type=Path, default=Path("storage/question_bank_v2"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    archive = sub.add_parser("archive-legacy")
    archive.add_argument("--source", type=Path, default=Path("storage/question_bank"))
    archive.add_argument("--archive", type=Path, default=Path("storage/question_bank/legacy_archive/v1"))
    archive.add_argument("--acknowledge-difference", action="store_true")
    pilot = sub.add_parser("run-pilot")
    pilot.add_argument("--authorization-usd", default="0.20")
    pilot.add_argument("--idempotency-key", default="")
    pilot.add_argument("--confirm-paid", action="store_true")
    pilot.add_argument("--allow-estimated-gemini-cap", action="store_true")
    resume_pilot = sub.add_parser("resume-pilot")
    resume_pilot.add_argument("prior_run_id")
    resume_pilot.add_argument("--batch-index", type=int, default=1)
    resume_pilot.add_argument("--authorization-usd", default="0.225")
    resume_pilot.add_argument("--idempotency-key", default="")
    resume_pilot.add_argument("--confirm-paid", action="store_true")
    resume_pilot.add_argument("--allow-estimated-gemini-cap", action="store_true")
    production = sub.add_parser("run-production-batch")
    production.add_argument("--batch-index", type=int, required=True)
    production.add_argument("--prior-run-id")
    production.add_argument("--authorization-usd", default="2.00")
    production.add_argument("--attempt-limit", type=int, default=100)
    production.add_argument("--uncertainty-review-limit", type=int, default=6)
    production.add_argument("--idempotency-key", default="")
    production.add_argument("--confirm-paid", action="store_true")
    production.add_argument("--allow-estimated-gemini-cap", action="store_true")
    reprocess = sub.add_parser("reprocess-candidates")
    reprocess.add_argument("--source-candidate-id", action="append", required=True)
    reprocess.add_argument("--batch-index", type=int, required=True)
    reprocess.add_argument("--prior-run-id")
    reprocess.add_argument("--authorization-usd", default="2.00")
    reprocess.add_argument("--attempt-limit", type=int, default=100)
    reprocess.add_argument("--uncertainty-review-limit", type=int, default=6)
    reprocess.add_argument("--idempotency-key", default="")
    reprocess.add_argument("--confirm-paid", action="store_true")
    reprocess.add_argument("--allow-estimated-gemini-cap", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("run_id")
    review = sub.add_parser("review-resolve")
    review.add_argument("case_id")
    review.add_argument("action", choices=("accept", "reject", "pass", "fail", "hold"))
    review.add_argument("--reason", action="append", default=[])
    review.add_argument("--metadata-json", default="")
    review.add_argument("--idempotency-key", default="")
    snapshot = sub.add_parser("snapshot-build")
    snapshot.add_argument("campaign_run_id")
    snapshot.add_argument("--idempotency-key", default="")
    verify = sub.add_parser("release-verify")
    verify.add_argument("snapshot_id")
    regression = sub.add_parser("regression-record")
    regression.add_argument("snapshot_id")
    regression.add_argument("signature")
    regression.add_argument("--passed", action="store_true")
    spot_select = sub.add_parser("spot-check-select")
    spot_select.add_argument("snapshot_id")
    spot_record = sub.add_parser("spot-check-record")
    spot_record.add_argument("snapshot_id")
    spot_record.add_argument("signature")
    spot_record.add_argument("--passed", action="store_true")
    publish = sub.add_parser("release-publish")
    publish.add_argument("snapshot_id")
    publish.add_argument("--idempotency-key", default="")
    withdraw = sub.add_parser("release-withdraw")
    withdraw.add_argument("reason")
    withdraw.add_argument("--idempotency-key", default="")
    rollback = sub.add_parser("release-rollback")
    rollback.add_argument("snapshot_id")
    rollback.add_argument("--idempotency-key", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    root: Path = args.root
    config = _configuration()
    if args.command == "init":
        store = V2Store(root)
        store.install_configuration(config)
        _print({"configuration_id": config.manifest_id, "snapshot_id": store.ensure_empty_snapshot()})
        store.close()
        return 0
    if args.command == "archive-legacy":
        expected = {"accepted_questions": 0, "open_review_cases": 418, "agent_invocations": 143, "taxonomy_versions": 1}
        _print(archive_legacy_storage(
            args.source, args.archive, expected_inventory=expected,
            acknowledge_difference=args.acknowledge_difference,
        ))
        return 0
    if args.command in {
        "run-pilot",
        "resume-pilot",
        "run-production-batch",
        "reprocess-candidates",
    }:
        if not args.confirm_paid:
            raise SystemExit(f"{args.command} requires --confirm-paid and a separate explicit authorization")
        if not args.allow_estimated_gemini_cap:
            raise SystemExit(
                f"{args.command} requires --allow-estimated-gemini-cap because Gemini high thinking has no documented reasoning-inclusive hard cap"
            )
        provider = ProviderRouter(
            openai=NativeOpenAIAdapter(),
            gemini=NativeGeminiAdapter(allow_estimated_total_generated_cap=True),
        )
        embedder = FastEmbedAdapter(checksum=config.embedding_checksum)
        engine = EnrichmentEngine(root, provider=provider, configuration=config, embedder=embedder)
        if args.command in {"run-pilot", "resume-pilot"}:
            request = RunRequest.pilot(
                idempotency_key=args.idempotency_key or f"{args.command}-{uuid.uuid4().hex}",
                snapshot_id=engine.empty_snapshot_id,
                authorization_usd=args.authorization_usd,
                configuration_id=config.manifest_id,
                batch_index=getattr(args, "batch_index", 0),
            )
            result = (
                engine.resume(args.prior_run_id, request)
                if args.command == "resume-pilot"
                else engine.run(request)
            )
        elif args.command == "run-production-batch":
            request = RunRequest.production_batch(
                idempotency_key=args.idempotency_key or f"production-{args.batch_index}-{uuid.uuid4().hex}",
                snapshot_id=engine.empty_snapshot_id,
                batch_index=args.batch_index,
                authorization_usd=args.authorization_usd,
                attempt_limit=args.attempt_limit,
                uncertainty_review_limit=args.uncertainty_review_limit,
                configuration_id=config.manifest_id,
            )
            result = (
                engine.continue_campaign(args.prior_run_id, request)
                if args.prior_run_id else engine.run(request)
            )
        else:
            request = RunRequest.production_batch(
                idempotency_key=(
                    args.idempotency_key
                    or f"reprocess-{args.batch_index}-{uuid.uuid4().hex}"
                ),
                snapshot_id=engine.empty_snapshot_id,
                batch_index=args.batch_index,
                authorization_usd=args.authorization_usd,
                attempt_limit=args.attempt_limit,
                uncertainty_review_limit=args.uncertainty_review_limit,
                configuration_id=config.manifest_id,
            )
            result = engine.reprocess_candidates(
                request,
                tuple(args.source_candidate_id),
                prior_run_id=args.prior_run_id,
            )
        _print(result); engine.close(); return 0
    if args.command == "report":
        review = HumanReview(root); _print(review.run_report(args.run_id)); review.close(); return 0
    if args.command == "review-resolve":
        review = HumanReview(root)
        resolution = {"action": args.action, "reason_codes": args.reason}
        if args.metadata_json:
            metadata = json.loads(args.metadata_json)
            if not isinstance(metadata, dict):
                raise SystemExit("--metadata-json must decode to a JSON object")
            resolution["metadata"] = metadata
        _print(review.resolve(
            args.case_id, resolution,
            idempotency_key=args.idempotency_key or f"review-{uuid.uuid4().hex}",
        ))
        review.close(); return 0
    release = _release(root)
    try:
        key = getattr(args, "idempotency_key", "") or f"{args.command}-{uuid.uuid4().hex}"
        if args.command == "snapshot-build":
            _print({
                "snapshot_id": release.build_candidate_snapshot(
                    args.campaign_run_id, idempotency_key=key
                )
            })
        elif args.command == "release-verify":
            _print(release.verify(args.snapshot_id))
        elif args.command == "regression-record":
            _print({
                "record_id": release.record_regression(
                    args.snapshot_id,
                    fixture_hash=ReferenceFixture.load_default().fixture_hash,
                    passed=args.passed,
                    signature=args.signature,
                )
            })
        elif args.command == "spot-check-select":
            _print({"question_ids": release.select_spot_check(args.snapshot_id)})
        elif args.command == "spot-check-record":
            question_ids = release.select_spot_check(args.snapshot_id)
            _print({
                "record_id": release.record_spot_check(
                    args.snapshot_id,
                    question_ids=question_ids,
                    passed=args.passed,
                    signature=args.signature,
                ),
                "question_ids": question_ids,
            })
        elif args.command == "release-publish":
            _print(release.publish(args.snapshot_id, idempotency_key=key))
        elif args.command == "release-withdraw":
            _print(release.withdraw(reason=args.reason, idempotency_key=key))
        elif args.command == "release-rollback":
            _print(release.rollback(args.snapshot_id, idempotency_key=key))
    finally:
        release.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
