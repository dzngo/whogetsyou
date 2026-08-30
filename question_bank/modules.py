"""Deep deterministic modules around the semantic LLM agent graph."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from question_bank.contracts import (
    AdmissionDecision,
    CoveragePlan,
    CoverageRegion,
    CoverageRegionKind,
    CoverageReport,
    EnrichmentBrief,
    HumanResolution,
    NeighborEvidence,
    QuestionBankRelease,
    QuestionBankSnapshot,
    QuestionLevel,
    QuestionUsageEvent,
    ReleaseIntent,
    ReleaseReport,
    ResolutionResult,
    ReviewCase,
    ReviewRequest,
    TaxonomyCandidate,
    TaxonomyDecision,
    TaxonomyVersion,
    record_dict,
)
from question_bank.core import QuestionBank, _stable_hash


def _connection(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _tokens(text: str) -> Counter[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = [f"{word[i:i+3]}" for word in words for i in range(max(1, len(word) - 2))]
    return Counter(words + grams)


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return numerator / denominator if denominator else 0.0


class QuestionBankNeighborIndex:
    """Rebuildable lexical and token/ngram-cosine index with no verdict authority."""

    def __init__(self, bank: QuestionBank, limit: int = 12) -> None:
        self._bank = bank
        self._limit = limit

    def find_neighbors(self, candidate_fingerprint: Dict[str, str], snapshot_id: str) -> List[NeighborEvidence]:
        candidate_tokens = _tokens(candidate_fingerprint["text"])
        candidate_words = set(re.findall(r"[a-z0-9]+", candidate_fingerprint["text"].lower()))
        matches = []
        for revision in self._bank.list_revisions(snapshot_id):
            other_words = set(re.findall(r"[a-z0-9]+", revision.text.lower()))
            union = candidate_words | other_words
            lexical = len(candidate_words & other_words) / len(union) if union else 0.0
            ngram_cosine = _cosine(candidate_tokens, _tokens(revision.text))
            facet_bonus = sum(
                [
                    candidate_fingerprint.get("scenario") == revision.semantic_scenario,
                    candidate_fingerprint.get("perspective_id") == revision.perspective_id,
                    candidate_fingerprint.get("answer_space") == revision.answer_space,
                ]
            ) * 0.15
            rank = lexical + ngram_cosine + facet_bonus
            matches.append(
                (
                    rank,
                    NeighborEvidence(
                        revision.revision_id,
                        revision.text,
                        lexical,
                        ngram_cosine,
                        revision.semantic_scenario,
                        revision.perspective_id,
                        revision.answer_space,
                    ),
                )
            )
        return [evidence for _, evidence in sorted(matches, key=lambda pair: (-pair[0], pair[1].neighbor_revision_id))[: self._limit]]


class HumanReview:
    """Append-only cases and resolutions for admission, themes, and taxonomy."""

    def __init__(self, database_path: Path | str) -> None:
        self._db = _connection(database_path)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_cases (
                case_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL,
                case_type TEXT NOT NULL, proposal_id TEXT NOT NULL, status TEXT NOT NULL,
                packet_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS review_resolutions (
                resolution_id TEXT PRIMARY KEY, case_id TEXT UNIQUE NOT NULL, idempotency_key TEXT UNIQUE NOT NULL,
                action TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS human_admission_outcomes (
                outcome_id TEXT PRIMARY KEY, case_id TEXT UNIQUE NOT NULL, decision TEXT NOT NULL,
                resolution_id TEXT NOT NULL, original_packet_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def open_case(self, request: ReviewRequest) -> ReviewCase:
        row = self._db.execute("SELECT * FROM review_cases WHERE idempotency_key = ?", (request.idempotency_key,)).fetchone()
        if row:
            return self._case(row)
        case_id = f"review-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT INTO review_cases VALUES (?, ?, ?, ?, ?, 'open', ?, CURRENT_TIMESTAMP)",
                (case_id, request.request_id, request.idempotency_key, request.case_type, request.proposal_id, json.dumps(request.packet, sort_keys=True)),
            )
        return ReviewCase(case_id, request.request_id, request.case_type, "open", request.packet)

    def resolve(self, case_id: str, resolution: HumanResolution) -> ResolutionResult:
        existing = self._db.execute(
            "SELECT * FROM review_resolutions WHERE idempotency_key = ?", (resolution.idempotency_key,)
        ).fetchone()
        if existing:
            return ResolutionResult(existing["resolution_id"], existing["case_id"], existing["action"], "resolved")
        case = self._db.execute("SELECT * FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        if not case:
            raise KeyError(case_id)
        if case["status"] != "open":
            raise ValueError("review case is already resolved")
        if resolution.action not in {"accept", "reject", "edit", "hold", "resolve_themes"}:
            raise ValueError("unsupported human resolution")
        resolution_id = f"resolution-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT INTO review_resolutions VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (resolution_id, case_id, resolution.idempotency_key, resolution.action, json.dumps(record_dict(resolution), sort_keys=True)),
            )
            self._db.execute("UPDATE review_cases SET status = 'resolved' WHERE case_id = ?", (case_id,))
            if case["case_type"] == "admission" and resolution.action in {"accept", "reject"}:
                self._db.execute(
                    "INSERT INTO human_admission_outcomes VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        f"human-outcome-{uuid.uuid4().hex}",
                        case_id,
                        resolution.action,
                        resolution_id,
                        case["packet_json"],
                    ),
                )
        return ResolutionResult(resolution_id, case_id, resolution.action, "resolved")

    def list_open(self) -> List[ReviewCase]:
        return [self._case(row) for row in self._db.execute("SELECT * FROM review_cases WHERE status = 'open'")]

    def get_case(self, case_id: str) -> ReviewCase:
        row = self._db.execute("SELECT * FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        if not row:
            raise KeyError(case_id)
        return self._case(row)

    @staticmethod
    def _case(row: sqlite3.Row) -> ReviewCase:
        return ReviewCase(row["case_id"], row["request_id"], row["case_type"], row["status"], json.loads(row["packet_json"]))


class TaxonomyRegistry:
    """Versioned Aspect/Perspective candidates, decisions, and releases."""

    def __init__(self, database_path: Path | str) -> None:
        self._db = _connection(database_path)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS taxonomy_candidates (
                candidate_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, facet TEXT NOT NULL,
                label TEXT NOT NULL, payload_json TEXT NOT NULL, decision TEXT NOT NULL, reason_codes_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS taxonomy_versions (
                version_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, manifest_json TEXT NOT NULL,
                content_hash TEXT NOT NULL, released INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def evaluate_candidate(self, candidate: TaxonomyCandidate, taxonomy_context: Dict[str, Any]) -> TaxonomyDecision:
        existing = self._db.execute("SELECT * FROM taxonomy_candidates WHERE idempotency_key = ?", (candidate.idempotency_key,)).fetchone()
        if existing:
            return TaxonomyDecision(existing["candidate_id"], AdmissionDecision(existing["decision"]), tuple(json.loads(existing["reason_codes_json"])))
        reasons = []
        decision = AdmissionDecision.ACCEPT
        if len(set(candidate.supporting_concept_ids)) < 6:
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["insufficient_independent_support"]
        elif not taxonomy_context.get("specialists_passed") or not taxonomy_context.get("challenger_passed"):
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["taxonomy_evidence_uncertain"]
        elif int(taxonomy_context.get("shadow_agreement", 0)) < 2:
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["shadow_classifier_disagreement"]
        else:
            reasons = ["independent_support", "specialists_passed", "shadow_classifiers_agree"]
        with self._db:
            self._db.execute(
                "INSERT INTO taxonomy_candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate.candidate_id,
                    candidate.idempotency_key,
                    candidate.facet,
                    candidate.label,
                    json.dumps(record_dict(candidate), sort_keys=True),
                    decision.value,
                    json.dumps(reasons),
                ),
            )
        return TaxonomyDecision(candidate.candidate_id, decision, tuple(reasons))

    def release(self, candidate_taxonomy_version: Dict[str, Any]) -> TaxonomyVersion:
        key = candidate_taxonomy_version["idempotency_key"]
        existing = self._db.execute("SELECT * FROM taxonomy_versions WHERE idempotency_key = ?", (key,)).fetchone()
        if existing:
            return self._version(existing)
        candidate_ids = sorted(set(candidate_taxonomy_version["candidate_ids"]))
        candidates = []
        for candidate_id in candidate_ids:
            row = self._db.execute("SELECT * FROM taxonomy_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if not row or row["decision"] != AdmissionDecision.ACCEPT.value:
                raise ValueError("taxonomy release contains an unaccepted candidate")
            candidates.append(row)
        base_aspects: List[str] = []
        base_perspectives: List[str] = []
        base_candidate_ids: List[str] = []
        base_version_id = candidate_taxonomy_version.get("base_version_id")
        if base_version_id:
            base_row = self._db.execute(
                "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ? AND released = 1",
                (base_version_id,),
            ).fetchone()
            if not base_row:
                raise ValueError("taxonomy release base version is not released")
            base_manifest = json.loads(base_row[0])
            base_aspects = base_manifest["aspects"]
            base_perspectives = base_manifest["perspectives"]
            base_candidate_ids = base_manifest["candidate_ids"]
        aspects = sorted(
            set(base_aspects)
            | {
                row["label"].strip().lower().replace(" ", "_")
                for row in candidates
                if row["facet"] == "aspect"
            }
        )
        perspectives = sorted(
            set(base_perspectives)
            | {
                row["label"].strip().lower().replace(" ", "_")
                for row in candidates
                if row["facet"] == "perspective"
            }
        )
        manifest = {
            "base_version_id": base_version_id,
            "candidate_ids": sorted(set(base_candidate_ids) | set(candidate_ids)),
            "aspects": aspects,
            "perspectives": perspectives,
        }
        content_hash = _stable_hash(manifest)
        version_id = f"taxonomy-{content_hash[:16]}"
        with self._db:
            self._db.execute(
                "INSERT INTO taxonomy_versions VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)",
                (version_id, key, json.dumps(manifest, sort_keys=True), content_hash),
            )
        return TaxonomyVersion(version_id, tuple(aspects), tuple(perspectives), content_hash, True)

    def install_initial(
        self,
        idempotency_key: str,
        aspects: Iterable[str],
        perspectives: Iterable[str],
    ) -> TaxonomyVersion:
        """Install the human-confirmed initial vocabulary without the candidate path."""
        existing = self._db.execute(
            "SELECT * FROM taxonomy_versions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return self._version(existing)
        manifest = {
            "candidate_ids": [],
            "aspects": sorted(set(aspects)),
            "perspectives": sorted(set(perspectives)),
        }
        if not manifest["aspects"] or not manifest["perspectives"]:
            raise ValueError("initial taxonomy needs at least one Aspect and Perspective")
        content_hash = _stable_hash(manifest)
        version_id = f"taxonomy-{content_hash[:16]}"
        with self._db:
            self._db.execute(
                "INSERT INTO taxonomy_versions VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)",
                (version_id, idempotency_key, json.dumps(manifest, sort_keys=True), content_hash),
            )
        return TaxonomyVersion(
            version_id,
            tuple(manifest["aspects"]),
            tuple(manifest["perspectives"]),
            content_hash,
            True,
        )

    def current_version(self) -> TaxonomyVersion:
        row = self._db.execute(
            "SELECT * FROM taxonomy_versions WHERE released = 1 ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise ValueError("no released Taxonomy Version is installed")
        return self._version(row)

    def has_version(self, version_id: str) -> bool:
        return bool(
            self._db.execute(
                "SELECT 1 FROM taxonomy_versions WHERE version_id = ? AND released = 1",
                (version_id,),
            ).fetchone()
        )

    def definition_context(self, version_id: str) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ? AND released = 1",
            (version_id,),
        ).fetchone()
        if not row:
            raise KeyError(version_id)
        manifest = json.loads(row[0])
        return {
            "version_id": version_id,
            "aspects": [
                {"id": taxon, "definition": taxon.replace("_", " ")}
                for taxon in manifest["aspects"]
            ],
            "perspectives": [
                {"id": taxon, "definition": taxon.replace("_", " ")}
                for taxon in manifest["perspectives"]
            ],
        }

    @staticmethod
    def _version(row: sqlite3.Row) -> TaxonomyVersion:
        manifest = json.loads(row["manifest_json"])
        return TaxonomyVersion(row["version_id"], tuple(manifest["aspects"]), tuple(manifest["perspectives"]), row["content_hash"], bool(row["released"]))


class CoveragePlanner:
    """Versioned meaningful regions and deterministic gap ordering."""

    def __init__(self, database_path: Path | str, bank: QuestionBank) -> None:
        self._db = _connection(database_path)
        self._bank = bank
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS coverage_plans (
                plan_id TEXT PRIMARY KEY, taxonomy_version_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coverage_reports (
                report_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, snapshot_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def plan(self, taxonomy_version: Dict[str, Any]) -> CoveragePlan:
        regions = taxonomy_version.get("regions", [])
        if not all(isinstance(region, CoverageRegion) for region in regions):
            raise ValueError("coverage regions must be explicitly classified")
        payload = [record_dict(region) for region in regions]
        plan_id = f"coverage-{_stable_hash([taxonomy_version['version_id'], payload])[:16]}"
        plan = CoveragePlan(plan_id, taxonomy_version["version_id"], list(regions))
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO coverage_plans VALUES (?, ?, ?)",
                (plan_id, plan.taxonomy_version_id, json.dumps(record_dict(plan), sort_keys=True)),
            )
        return plan

    def measure(
        self,
        snapshot_id: str,
        coverage_plan_id: str,
        include_staged: bool = False,
    ) -> CoverageReport:
        row = self._db.execute("SELECT payload_json FROM coverage_plans WHERE plan_id = ?", (coverage_plan_id,)).fetchone()
        if not row:
            raise KeyError(coverage_plan_id)
        raw = json.loads(row[0])
        revisions = self._bank.list_revisions(snapshot_id)
        counts: Dict[str, int] = {}
        scenario_counts: Dict[str, int] = {}
        gaps = set()
        concentration_alerts = set()
        horizon_revisions: Dict[tuple[str, str], list] = {}
        for region in raw["regions"]:
            matching = [
                revision
                for revision in revisions
                if (revision.lifecycle == "active" or include_staged)
                and region["theme_id"] in revision.theme_memberships
                and region["level"] == revision.level
                and region["aspect_id"] == revision.aspect_id
                and region["perspective_id"] == revision.perspective_id
            ]
            counts[region["region_id"]] = len(matching)
            scenario_counts[region["region_id"]] = len({revision.semantic_scenario for revision in matching})
            answer_space_count = len(
                {revision.answer_space.strip().lower() for revision in matching}
            )
            if region["kind"] == CoverageRegionKind.REQUIRED.value and (
                scenario_counts[region["region_id"]]
                < int(region["minimum_distinct_scenarios"])
                or answer_space_count < 2
            ):
                gaps.add(region["region_id"])
            for facet_name, values in (
                ("answer_space", [revision.answer_space for revision in matching]),
                ("wording_pattern", [revision.wording_pattern for revision in matching]),
            ):
                if len(values) >= 3:
                    frequency = Counter(value.strip().lower() for value in values)
                    if max(frequency.values()) / len(values) > 0.75:
                        concentration_alerts.add(
                            f"region:{region['region_id']}:{facet_name}"
                        )
                        if region["kind"] == CoverageRegionKind.REQUIRED.value:
                            gaps.add(region["region_id"])
            horizon_revisions.setdefault(
                (region["theme_id"], region["level"]), []
            ).extend(matching)
        required_by_horizon: Dict[tuple[str, str], list[str]] = {}
        for region in raw["regions"]:
            if region["kind"] == CoverageRegionKind.REQUIRED.value:
                required_by_horizon.setdefault(
                    (region["theme_id"], region["level"]), []
                ).append(region["region_id"])
        for horizon, matching in horizon_revisions.items():
            unique = {revision.revision_id: revision for revision in matching}.values()
            unique_list = list(unique)
            for facet_name, values in (
                ("answer_space", [revision.answer_space for revision in unique_list]),
                ("wording_pattern", [revision.wording_pattern for revision in unique_list]),
            ):
                if len(values) >= 6:
                    frequency = Counter(value.strip().lower() for value in values)
                    if max(frequency.values()) / len(values) > 0.60:
                        concentration_alerts.add(
                            f"horizon:{horizon[0]}:{horizon[1]}:{facet_name}"
                        )
                        gaps.update(required_by_horizon.get(horizon, []))
        report_id = f"report-{_stable_hash([coverage_plan_id, snapshot_id, counts, scenario_counts, sorted(concentration_alerts)])[:16]}"
        report = CoverageReport(
            report_id,
            coverage_plan_id,
            snapshot_id,
            counts,
            scenario_counts,
            tuple(sorted(gaps)),
            tuple(sorted(concentration_alerts)),
        )
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO coverage_reports VALUES (?, ?, ?, ?)",
                (report_id, coverage_plan_id, snapshot_id, json.dumps(record_dict(report), sort_keys=True)),
            )
        return report

    def current_plan(self, taxonomy_version_id: Optional[str] = None) -> CoveragePlan:
        if taxonomy_version_id:
            row = self._db.execute(
                "SELECT payload_json FROM coverage_plans WHERE taxonomy_version_id = ? ORDER BY rowid DESC LIMIT 1",
                (taxonomy_version_id,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT payload_json FROM coverage_plans ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if not row:
            raise ValueError("no Coverage Plan is installed for the released taxonomy")
        raw = json.loads(row[0])
        regions = [
            CoverageRegion(
                region["region_id"],
                region["theme_id"],
                QuestionLevel(region["level"]),
                region["aspect_id"],
                region["perspective_id"],
                CoverageRegionKind(region["kind"]),
                int(region["minimum_distinct_scenarios"]),
            )
            for region in raw["regions"]
        ]
        return CoveragePlan(
            raw["plan_id"],
            raw["taxonomy_version_id"],
            regions,
            raw["policy_version"],
        )

    def next_gaps(self, coverage_report: CoverageReport) -> List[EnrichmentBrief]:
        plan_row = self._db.execute("SELECT payload_json FROM coverage_plans WHERE plan_id = ?", (coverage_report.plan_id,)).fetchone()
        raw = json.loads(plan_row[0])
        regions = {region["region_id"]: region for region in raw["regions"]}
        briefs = []
        for region_id in sorted(coverage_report.gaps, key=lambda key: (coverage_report.scenario_counts.get(key, 0), key)):
            region = regions[region_id]
            brief_seed = [coverage_report.report_id, region_id]
            briefs.append(
                EnrichmentBrief(
                    brief_id=f"brief-{_stable_hash(brief_seed)[:16]}",
                    idempotency_key=f"brief-key-{_stable_hash(brief_seed)[:16]}",
                    level=QuestionLevel(region["level"]),
                    coverage_gap=region,
                    taxonomy_version_id=raw["taxonomy_version_id"],
                    snapshot_id=coverage_report.snapshot_id,
                )
            )
        return briefs


class CompletionChallenge:
    """Versioned diminishing-returns rule; weak or failed agents cannot declare completion."""

    def __init__(
        self,
        required_rounds: int = 3,
        minimum_strategies: int = 2,
        minimum_concepts_per_strategy: int = 20,
        maximum_distinct_yield: float = 0.05,
    ) -> None:
        self.required_rounds = required_rounds
        self.minimum_strategies = minimum_strategies
        self.minimum_concepts_per_strategy = minimum_concepts_per_strategy
        self.maximum_distinct_yield = maximum_distinct_yield

    def is_complete(self, horizons_healthy: bool, rounds: List[Dict[str, Any]]) -> bool:
        if not horizons_healthy or len(rounds) != self.required_rounds:
            return False
        for round_result in rounds:
            strategies = round_result.get("strategies", [])
            if len(strategies) < self.minimum_strategies:
                return False
            total_concepts = 0
            total_accepted = 0
            for strategy in strategies:
                concepts = int(strategy.get("concepts", 0))
                accepted = int(strategy.get("accepted_distinct", 0))
                if concepts < self.minimum_concepts_per_strategy:
                    return False
                if accepted / concepts >= self.maximum_distinct_yield:
                    return False
                if int(strategy.get("new_valid_regions", 0)):
                    return False
                if strategy.get("dominant_rejection") not in {"semantic_repeat", "coverage_redundancy"}:
                    return False
                total_concepts += concepts
                total_accepted += accepted
            if total_accepted / total_concepts >= self.maximum_distinct_yield:
                return False
        return True


class ReferenceExampleRegistry:
    """Human-confirmed initial calibration set and versioned regression results."""

    def __init__(self, database_path: Path | str, minimum_confirmed: int = 30) -> None:
        self._db = _connection(database_path)
        self.minimum_confirmed = minimum_confirmed
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS reference_examples (
                example_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
                confirmed INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reference_regressions (
                regression_id TEXT PRIMARY KEY, policy_hash TEXT NOT NULL,
                result_json TEXT NOT NULL, passed INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def import_examples(self, examples: List[Dict[str, Any]], confirmed: bool = False) -> int:
        with self._db:
            for example in examples:
                if not example.get("example_id") or not example.get("question") or not example.get("expected_decision"):
                    raise ValueError("each Reference Example needs id, question, and expected_decision")
                self._db.execute(
                    "INSERT OR IGNORE INTO reference_examples VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (example["example_id"], json.dumps(example, sort_keys=True), int(confirmed)),
                )
        return len(examples)

    def confirm(self, example_ids: Iterable[str]) -> int:
        identifiers = sorted(set(example_ids))
        with self._db:
            for example_id in identifiers:
                cursor = self._db.execute(
                    "UPDATE reference_examples SET confirmed = 1 WHERE example_id = ?",
                    (example_id,),
                )
                if not cursor.rowcount:
                    raise KeyError(example_id)
        return len(identifiers)

    def record_regression(
        self,
        policy_versions: Dict[str, str],
        results: Dict[str, bool],
    ) -> str:
        confirmed = {
            row["example_id"]
            for row in self._db.execute(
                "SELECT example_id FROM reference_examples WHERE confirmed = 1"
            )
        }
        if len(confirmed) < self.minimum_confirmed:
            raise ValueError("at least 30 human-confirmed Reference Examples are required")
        if set(results) != confirmed:
            raise ValueError("regression results must cover every confirmed Reference Example")
        passed = all(results.values())
        policy_hash = _stable_hash(policy_versions)
        regression_id = f"reference-regression-{_stable_hash([policy_hash, results])[:20]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO reference_regressions VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (regression_id, policy_hash, json.dumps(results, sort_keys=True), int(passed)),
            )
        return regression_id

    def latest_regression_passed(self, policy_versions: Dict[str, str]) -> bool:
        row = self._db.execute(
            """SELECT passed FROM reference_regressions WHERE policy_hash = ?
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (_stable_hash(policy_versions),),
        ).fetchone()
        return bool(row and row[0])


class ReleaseModule:
    """Immutable candidates, release gates, atomic current pointer, and rollback."""

    def __init__(
        self,
        database_path: Path | str,
        bank: QuestionBank,
        taxonomy: TaxonomyRegistry,
        coverage: CoveragePlanner,
        references: ReferenceExampleRegistry,
        revalidator: Callable[[list, list, str, Dict[str, Any]], Dict[str, bool]],
    ) -> None:
        # Release manifests and the current pointer share the trusted bank DB so
        # publication and lifecycle activation commit atomically.
        self._db = _connection(bank.database_path)
        self._bank = bank
        self._taxonomy = taxonomy
        self._coverage = coverage
        self._references = references
        self._revalidator = revalidator
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS release_candidates (
                candidate_snapshot_id TEXT PRIMARY KEY, bank_snapshot_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL, intent_json TEXT NOT NULL,
                release_content_hash TEXT NOT NULL, report_json TEXT,
                published INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS releases (
                release_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS release_pointer (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1), snapshot_id TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def build_candidate(self, release_intent: ReleaseIntent):
        existing = self._db.execute(
            "SELECT * FROM release_candidates WHERE idempotency_key = ?",
            (release_intent.idempotency_key,),
        ).fetchone()
        if existing:
            intent = json.loads(existing["intent_json"])
            return QuestionBankSnapshot(
                existing["candidate_snapshot_id"],
                tuple(sorted(intent["revision_ids"])),
                existing["release_content_hash"],
            )
        snapshot = self._bank.snapshot({"revision_ids": release_intent.revision_ids})
        intent_json = json.dumps(record_dict(release_intent), sort_keys=True)
        release_content_hash = _stable_hash(
            {"bank_content_hash": snapshot.content_hash, "release_intent": json.loads(intent_json)}
        )
        candidate_snapshot_id = f"bank-candidate-{release_content_hash[:20]}"
        with self._db:
            self._db.execute(
                """INSERT INTO release_candidates(
                       candidate_snapshot_id, bank_snapshot_id, idempotency_key,
                       intent_json, release_content_hash
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    candidate_snapshot_id,
                    snapshot.snapshot_id,
                    release_intent.idempotency_key,
                    intent_json,
                    release_content_hash,
                ),
            )
        return QuestionBankSnapshot(
            candidate_snapshot_id,
            snapshot.revision_ids,
            release_content_hash,
        )

    def verify(self, candidate_snapshot_id: str) -> ReleaseReport:
        row = self._db.execute(
            "SELECT * FROM release_candidates WHERE candidate_snapshot_id = ?",
            (candidate_snapshot_id,),
        ).fetchone()
        if not row:
            raise KeyError(candidate_snapshot_id)
        intent = json.loads(row["intent_json"])
        snapshot = self._bank.snapshot_record(row["bank_snapshot_id"])
        rebuilt = self._bank.snapshot({"revision_ids": snapshot.revision_ids})
        release_content_hash = _stable_hash(
            {"bank_content_hash": rebuilt.content_hash, "release_intent": intent}
        )
        revisions = self._bank.list_revisions(snapshot.snapshot_id)
        packages = [
            self._bank.admission_package_record(revision.revision_id)
            for revision in revisions
        ]
        revalidation_gates = self._revalidator(
            revisions,
            packages,
            snapshot.snapshot_id,
            intent,
        )
        question_ids = [revision.question_id for revision in revisions]
        normalized_texts = [" ".join(revision.text.lower().split()) for revision in revisions]
        facet_triples = [
            (
                revision.semantic_scenario.strip().lower(),
                revision.perspective_id,
                revision.answer_space.strip().lower(),
            )
            for revision in revisions
        ]
        try:
            plan = self._coverage.current_plan(intent["taxonomy_version_id"])
            coverage_report = self._coverage.measure(
                snapshot.snapshot_id,
                plan.plan_id,
                include_staged=True,
            )
            coverage_ok = (
                plan.plan_id == intent["coverage_plan_id"]
                and not coverage_report.gaps
                and not coverage_report.concentration_alerts
            )
        except (KeyError, ValueError):
            coverage_ok = False
        first_index = QuestionBankNeighborIndex(self._bank, limit=max(1, len(revisions)))
        second_index = QuestionBankNeighborIndex(self._bank, limit=max(1, len(revisions)))
        first_projection = []
        second_projection = []
        for revision in revisions:
            fingerprint = {
                "text": revision.text,
                "scenario": revision.semantic_scenario,
                "perspective_id": revision.perspective_id,
                "answer_space": revision.answer_space,
            }
            first_projection.append(
                [record_dict(item) for item in first_index.find_neighbors(fingerprint, snapshot.snapshot_id)]
            )
            second_projection.append(
                [record_dict(item) for item in second_index.find_neighbors(fingerprint, snapshot.snapshot_id)]
            )
        gates = {
            "content_hash": rebuilt.content_hash == snapshot.content_hash,
            "release_manifest_hash": release_content_hash == row["release_content_hash"],
            "nonempty": bool(revisions),
            "no_retired": all(revision.lifecycle != "retired" for revision in revisions),
            "one_revision_per_question": len(question_ids) == len(set(question_ids)),
            "provenance": all(bool(revision.provenance) for revision in revisions),
            "evidence": all(bool(revision.evidence_id) for revision in revisions),
            "complete_evaluation": all(
                package["evidence"]["complete"]
                and len(package["evidence"]["judge_invocation_ids"]) >= 5
                and package["outcome"]["decision"] == "accept"
                for package in packages
            ),
            "resolved_theme": all(
                package["theme_classification"]["resolved"]
                and (
                    len(package["theme_classification"]["classifier_invocation_ids"]) >= 2
                    or package["theme_classification"]["classification_id"].startswith(
                        "human-themes-"
                    )
                )
                for package in packages
            ),
            "scoped_revalidation": all(
                package["taxonomy_version_id"] == intent["taxonomy_version_id"]
                for package in packages
            )
            and all(revalidation_gates.values()),
            "exact_text_distinctness": len(normalized_texts) == len(set(normalized_texts)),
            "semantic_facet_distinctness": len(facet_triples) == len(set(facet_triples)),
            "taxonomy": self._taxonomy.has_version(intent["taxonomy_version_id"]),
            "coverage": coverage_ok,
            "index_equivalence": first_projection == second_projection,
            "reference_examples": self._references.latest_regression_passed(intent["policy_versions"]),
            "spot_check": bool(intent["spot_check_passed"]),
            "policy_versions": bool(intent["policy_versions"]),
            **revalidation_gates,
        }
        passed = all(gates.values())
        reasons = tuple(sorted(key for key, value in gates.items() if not value))
        report = ReleaseReport(candidate_snapshot_id, passed, gates, reasons)
        with self._db:
            self._db.execute(
                "UPDATE release_candidates SET report_json = ? WHERE candidate_snapshot_id = ?",
                (json.dumps(record_dict(report), sort_keys=True), candidate_snapshot_id),
            )
        return report

    def publish(self, candidate_snapshot_id: str) -> QuestionBankRelease:
        report = self.verify(candidate_snapshot_id)
        if not report.passed:
            raise ValueError(f"release gates failed: {', '.join(report.reason_codes)}")
        candidate = self._db.execute(
            "SELECT * FROM release_candidates WHERE candidate_snapshot_id = ?",
            (candidate_snapshot_id,),
        ).fetchone()
        self._bank.snapshot_record(candidate["bank_snapshot_id"])
        release_hash = candidate["release_content_hash"]
        release_id = f"bank-{release_hash[:16]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO releases VALUES (?, ?, ?, 'released', CURRENT_TIMESTAMP)",
                (release_id, candidate_snapshot_id, release_hash),
            )
            self._db.execute(
                "INSERT INTO release_pointer(singleton, snapshot_id) VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET snapshot_id = excluded.snapshot_id",
                (candidate_snapshot_id,),
            )
            self._db.execute(
                "UPDATE release_candidates SET published = 1 WHERE candidate_snapshot_id = ?",
                (candidate_snapshot_id,),
            )
            self._db.execute(
                "UPDATE snapshots SET status = 'released' WHERE snapshot_id = ?",
                (candidate["bank_snapshot_id"],),
            )
            manifest = self._db.execute(
                "SELECT manifest_json FROM snapshots WHERE snapshot_id = ?",
                (candidate["bank_snapshot_id"],),
            ).fetchone()[0]
            revision_ids = [item[0] for item in json.loads(manifest)]
            if revision_ids:
                placeholders = ",".join("?" for _ in revision_ids)
                self._db.execute(
                    f"UPDATE question_revisions SET lifecycle = 'active' WHERE revision_id IN ({placeholders})",
                    revision_ids,
                )
        return QuestionBankRelease(release_id, candidate_snapshot_id, release_hash, "released")

    def rollback(self, snapshot_id: str) -> QuestionBankRelease:
        candidate = self._db.execute(
            "SELECT * FROM release_candidates WHERE candidate_snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if not candidate:
            raise ValueError("rollback target must be a previously released immutable snapshot")
        self._bank.snapshot_record(candidate["bank_snapshot_id"])
        prior = self._db.execute(
            """SELECT content_hash FROM releases
               WHERE snapshot_id = ? AND status = 'released'
               ORDER BY created_at DESC LIMIT 1""",
            (snapshot_id,),
        ).fetchone()
        if not prior:
            raise ValueError("rollback target has no release manifest")
        release_id = f"rollback-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT INTO releases VALUES (?, ?, ?, 'rollback', CURRENT_TIMESTAMP)",
                (release_id, snapshot_id, prior[0]),
            )
            self._db.execute(
                "INSERT INTO release_pointer(singleton, snapshot_id) VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET snapshot_id = excluded.snapshot_id",
                (snapshot_id,),
            )
        return QuestionBankRelease(release_id, snapshot_id, prior[0], "rollback")

    def current_snapshot_id(self) -> Optional[str]:
        row = self._db.execute("SELECT snapshot_id FROM release_pointer WHERE singleton = 1").fetchone()
        return row[0] if row else None

    def current_bank_snapshot_id(self) -> Optional[str]:
        candidate_id = self.current_snapshot_id()
        if not candidate_id:
            return None
        row = self._db.execute(
            "SELECT bank_snapshot_id FROM release_candidates WHERE candidate_snapshot_id = ?",
            (candidate_id,),
        ).fetchone()
        return row[0] if row else None


class QuestionUsageSink:
    """Write-only, separate telemetry database with 90-day raw retention."""

    ALLOWED_TYPES = {"presented", "skipped", "edit_completed", "confirmed", "round_finished"}

    def __init__(self, database_path: Path | str, retention_days: int = 90) -> None:
        self._db = _connection(database_path)
        self._retention_days = retention_days
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS usage_events (
                event_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def append(self, event: QuestionUsageEvent) -> Dict[str, Any]:
        if event.event_type not in self.ALLOWED_TYPES:
            raise ValueError("unsupported usage event type")
        if any(marker in event.origin.lower() for marker in ("answer=", "name=", "guess=", "score=", "ip=")):
            raise ValueError("origin cannot contain private gameplay data")
        existing = self._db.execute("SELECT event_id FROM usage_events WHERE idempotency_key = ?", (event.idempotency_key,)).fetchone()
        if existing:
            return {"appended": False, "event_id": existing[0]}
        with self._db:
            self._db.execute(
                "INSERT INTO usage_events VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (event.event_id, event.idempotency_key, json.dumps(record_dict(event), sort_keys=True)),
            )
        return {"appended": True, "event_id": event.event_id}

    def expire_raw(self, now: Optional[datetime] = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=self._retention_days)
        with self._db:
            cursor = self._db.execute(
                "DELETE FROM usage_events WHERE created_at < ?",
                (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
            )
        return cursor.rowcount
