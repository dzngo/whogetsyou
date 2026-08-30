"""Executable offline operator CLI for enrichment, review, and releases."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from models import DEFAULT_THEMES
from question_bank.agents import (
    AgentRunner,
    ProposalEvaluation,
    ProposalProduction,
    ReleaseRevalidator,
    TaxonomyAgentGroup,
    ThemeClassifier,
)
from question_bank.autonomy import AutonomousEnrichmentLoop
from question_bank.contracts import (
    DEFAULT_POLICY_VERSIONS,
    CoverageRegion,
    CoverageRegionKind,
    EnrichmentBrief,
    HumanResolution,
    QuestionLevel,
    ReleaseIntent,
    record_dict,
)
from question_bank.core import AdmissionDecider, QuestionBank
from question_bank.modules import (
    CoveragePlanner,
    HumanReview,
    QuestionBankNeighborIndex,
    ReferenceExampleRegistry,
    ReleaseModule,
    TaxonomyRegistry,
)
from question_bank.orchestrator import PipelineOrchestrator


class Runtime:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.bank = QuestionBank(root / "question_bank.sqlite3")
        self.workflow_path = root / "workflow.sqlite3"
        self.runner = AgentRunner(self.workflow_path)
        self.review = HumanReview(self.workflow_path)
        self.taxonomy = TaxonomyRegistry(self.workflow_path)
        self.coverage = CoveragePlanner(self.workflow_path, self.bank)
        self.references = ReferenceExampleRegistry(self.workflow_path)
        self.release = ReleaseModule(
            self.workflow_path,
            self.bank,
            self.taxonomy,
            self.coverage,
            self.references,
            ReleaseRevalidator(
                self.runner,
                QuestionBankNeighborIndex(self.bank),
                self.taxonomy.definition_context,
            ).revalidate,
        )
        self.orchestrator = PipelineOrchestrator(
            self.workflow_path,
            ProposalProduction(self.runner),
            ProposalEvaluation(self.runner, QuestionBankNeighborIndex(self.bank), AdmissionDecider()),
            ThemeClassifier(self.runner),
            self.bank,
            self.review,
            DEFAULT_THEMES,
            self.taxonomy.definition_context,
        )
        self.autonomy = AutonomousEnrichmentLoop(
            self.taxonomy,
            self.coverage,
            self.bank,
            self.orchestrator,
            self.review,
            self.release,
            taxonomy_agents=TaxonomyAgentGroup(self.runner, self.taxonomy),
        )

    def close(self) -> None:
        self.orchestrator.close()
        self.release.close()
        self.review.close()
        self.coverage.close()
        self.taxonomy.close()
        self.references.close()
        self.runner.close()
        self.bank.close()


def _json(value: Any) -> None:
    print(json.dumps(record_dict(value) if hasattr(value, "__dataclass_fields__") else value, indent=2, sort_keys=True))


def _brief(args: argparse.Namespace, runtime: Runtime, iteration: int = 0) -> EnrichmentBrief:
    gap = json.loads(args.gap_json)
    snapshot_id = args.snapshot_id
    if not snapshot_id:
        snapshot_id = runtime.release.current_bank_snapshot_id()
    if not snapshot_id:
        snapshot_id = runtime.bank.snapshot({"revision_ids": []}).snapshot_id
    seed = f"{args.level}:{args.taxonomy_version}:{snapshot_id}:{json.dumps(gap, sort_keys=True)}:{iteration}"
    digest = uuid.uuid5(uuid.NAMESPACE_URL, seed).hex
    return EnrichmentBrief(
        f"brief-{digest}",
        f"enrichment-{digest}",
        QuestionLevel(args.level),
        gap,
        args.taxonomy_version,
        snapshot_id,
        args.concepts_per_scout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="question-bank", description="Offline autonomous Question Bank enrichment")
    parser.add_argument("--data-dir", type=Path, default=Path("storage/question_bank"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize relational stores and an empty candidate snapshot")

    def enrichment_arguments(command):
        command.add_argument("--level", choices=[level.value for level in QuestionLevel], required=True)
        command.add_argument("--gap-json", required=True, help="Compact ontology gap; must not contain selected Theme")
        command.add_argument("--taxonomy-version", required=True)
        command.add_argument("--snapshot-id")
        command.add_argument("--concepts-per-scout", type=int, default=5)

    enrich = sub.add_parser("enrich", help="Run one idempotent enrichment brief")
    enrichment_arguments(enrich)
    autonomous = sub.add_parser(
        "autonomous",
        help="Select coverage gaps and run bounded autonomous enrichment",
    )
    autonomous.add_argument("--iterations", type=int, default=1)
    autonomous.add_argument("--concepts-per-scout", type=int, default=5)
    autonomous.add_argument("--max-open-reviews", type=int, default=100)
    autonomous.add_argument("--max-proposals", type=int, default=200)
    autonomous.add_argument("--auto-publish", action="store_true")
    autonomous.add_argument("--spot-check-passed", action="store_true")
    autonomous.add_argument("--run-completion-challenge", action="store_true")

    taxonomy_install = sub.add_parser(
        "taxonomy-install",
        help="Install the human-confirmed initial taxonomy",
    )
    taxonomy_install.add_argument("--aspect", action="append", required=True)
    taxonomy_install.add_argument("--perspective", action="append", required=True)
    coverage_install = sub.add_parser(
        "coverage-plan-install",
        help="Install a versioned Required/Exploratory/Invalid plan",
    )
    coverage_install.add_argument("--taxonomy-version", required=True)
    coverage_install.add_argument("--regions-file", type=Path, required=True)
    reference_import = sub.add_parser(
        "reference-import",
        help="Import agent-prepared Reference Examples",
    )
    reference_import.add_argument("--file", type=Path, required=True)
    reference_import.add_argument("--confirmed", action="store_true")
    reference_confirm = sub.add_parser(
        "reference-confirm",
        help="Confirm prepared Reference Example IDs",
    )
    reference_confirm.add_argument("example_id", nargs="+")
    reference_regression = sub.add_parser(
        "reference-regression-record",
        help="Record complete structured regression results for a policy set",
    )
    reference_regression.add_argument("--results-file", type=Path, required=True)
    reference_regression.add_argument("--policy-json", required=True)

    sub.add_parser("review-list", help="List unresolved human review cases")
    resolve = sub.add_parser("review-resolve", help="Append an immutable human resolution")
    resolve.add_argument("case_id")
    resolve.add_argument("action", choices=["accept", "reject", "edit", "hold", "resolve_themes"])
    resolve.add_argument("--reason", action="append", required=True)
    resolve.add_argument("--memberships", nargs="*")
    resolve.add_argument("--edited-text")

    build = sub.add_parser("release-build", help="Freeze a release candidate")
    build.add_argument("--revision-id", action="append", required=True)
    build.add_argument("--taxonomy-version", required=True)
    build.add_argument("--coverage-plan", required=True)
    build.add_argument("--spot-check-passed", action="store_true")
    verify = sub.add_parser("release-verify")
    verify.add_argument("snapshot_id")
    publish = sub.add_parser("release-publish")
    publish.add_argument("snapshot_id")
    rollback = sub.add_parser("release-rollback")
    rollback.add_argument("snapshot_id")
    sub.add_parser("status")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    runtime = Runtime(args.data_dir)
    try:
        if args.command == "init":
            _json(runtime.bank.snapshot({"revision_ids": []}))
        elif args.command == "enrich":
            _json(runtime.orchestrator.run_enrichment(_brief(args, runtime)))
        elif args.command == "autonomous":
            _json(
                runtime.autonomy.run(
                    max_iterations=args.iterations,
                    concepts_per_scout=args.concepts_per_scout,
                    max_proposals=args.max_proposals,
                    max_open_reviews=args.max_open_reviews,
                    auto_publish=args.auto_publish,
                    spot_check_passed=args.spot_check_passed,
                    run_completion_challenge=args.run_completion_challenge,
                )
            )
        elif args.command == "taxonomy-install":
            seed = "|".join(sorted(args.aspect + args.perspective))
            _json(
                runtime.taxonomy.install_initial(
                    f"initial-taxonomy-{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex}",
                    args.aspect,
                    args.perspective,
                )
            )
        elif args.command == "coverage-plan-install":
            raw_regions = json.loads(args.regions_file.read_text(encoding="utf-8"))
            regions = [
                CoverageRegion(
                    item["region_id"],
                    item["theme_id"],
                    QuestionLevel(item["level"]),
                    item["aspect_id"],
                    item["perspective_id"],
                    CoverageRegionKind(item["kind"]),
                    int(item.get("minimum_distinct_scenarios", 3)),
                )
                for item in raw_regions
            ]
            _json(
                runtime.coverage.plan(
                    {"version_id": args.taxonomy_version, "regions": regions}
                )
            )
        elif args.command == "reference-import":
            examples = json.loads(args.file.read_text(encoding="utf-8"))
            _json(
                {
                    "imported": runtime.references.import_examples(
                        examples,
                        confirmed=args.confirmed,
                    )
                }
            )
        elif args.command == "reference-confirm":
            _json({"confirmed": runtime.references.confirm(args.example_id)})
        elif args.command == "reference-regression-record":
            results = json.loads(args.results_file.read_text(encoding="utf-8"))
            policy_versions = json.loads(args.policy_json)
            _json(
                {
                    "regression_id": runtime.references.record_regression(
                        policy_versions,
                        results,
                    )
                }
            )
        elif args.command == "review-list":
            _json([record_dict(case) for case in runtime.review.list_open()])
        elif args.command == "review-resolve":
            resolution = HumanResolution(
                f"human-resolution-{uuid.uuid4().hex}", args.action, args.reason, args.memberships, args.edited_text
            )
            _json(runtime.orchestrator.resolve_review(args.case_id, resolution))
        elif args.command == "release-build":
            intent = ReleaseIntent(
                f"release-intent-{uuid.uuid4().hex}", args.revision_id, args.taxonomy_version,
                args.coverage_plan,
                dict(DEFAULT_POLICY_VERSIONS),
                args.spot_check_passed,
            )
            _json(runtime.release.build_candidate(intent))
        elif args.command == "release-verify":
            _json(runtime.release.verify(args.snapshot_id))
        elif args.command == "release-publish":
            _json(runtime.release.publish(args.snapshot_id))
        elif args.command == "release-rollback":
            _json(runtime.release.rollback(args.snapshot_id))
        elif args.command == "status":
            _json(
                {
                    "current_snapshot_id": runtime.release.current_snapshot_id(),
                    "question_revision_count": len(runtime.bank.list_revisions()),
                    "open_review_count": len(runtime.review.list_open()),
                    "creative_model": "gemini-3.5-flash-high",
                    "judge_model": "gpt-5.4-mini-high",
                }
            )
        return 0
    except (ValueError, KeyError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        runtime.close()
