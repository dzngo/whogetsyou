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
    DEFAULT_POLICY_VERSIONS,
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


def _semantic_scenario_count(revisions: Iterable[Any]) -> int:
    """Count conservative scenario families instead of distinct surface strings."""
    representatives: List[Counter[str]] = []
    for revision in revisions:
        fingerprint = _tokens(
            f"{revision.semantic_scenario} {revision.answer_space}"
        )
        if not any(_cosine(fingerprint, representative) >= 0.72 for representative in representatives):
            representatives.append(fingerprint)
    return len(representatives)


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
                action TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'resolved',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS human_admission_outcomes (
                outcome_id TEXT PRIMARY KEY, case_id TEXT UNIQUE NOT NULL, decision TEXT NOT NULL,
                resolution_id TEXT NOT NULL, original_packet_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        resolution_columns = {
            row["name"] for row in self._db.execute("PRAGMA table_info(review_resolutions)")
        }
        if "status" not in resolution_columns:
            self._db.execute(
                "ALTER TABLE review_resolutions ADD COLUMN status TEXT NOT NULL DEFAULT 'resolved'"
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
        self.begin_resolution(case_id, resolution)
        return self.complete_resolution(case_id, resolution)

    def begin_resolution(
        self, case_id: str, resolution: HumanResolution
    ) -> ResolutionResult:
        existing = self._db.execute(
            "SELECT * FROM review_resolutions WHERE idempotency_key = ?", (resolution.idempotency_key,)
        ).fetchone()
        if existing:
            if existing["case_id"] != case_id or existing["action"] != resolution.action:
                raise ValueError("resolution idempotency key conflicts with another action")
            return ResolutionResult(existing["resolution_id"], existing["case_id"], existing["action"], existing["status"])
        case = self._db.execute("SELECT * FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        if not case:
            raise KeyError(case_id)
        if case["status"] != "open":
            raise ValueError("review case is already resolved")
        if resolution.action not in {"accept", "reject", "edit", "hold", "resolve_themes", "resolve_region"}:
            raise ValueError("unsupported human resolution")
        resolution_id = self.resolution_id_for(case_id, resolution)
        with self._db:
            self._db.execute(
                """INSERT INTO review_resolutions(
                       resolution_id, case_id, idempotency_key, action, payload_json, status
                   ) VALUES (?, ?, ?, ?, ?, 'processing')""",
                (resolution_id, case_id, resolution.idempotency_key, resolution.action, json.dumps(record_dict(resolution), sort_keys=True)),
            )
            self._db.execute("UPDATE review_cases SET status = 'processing' WHERE case_id = ?", (case_id,))
        return ResolutionResult(resolution_id, case_id, resolution.action, "processing")

    def complete_resolution(
        self, case_id: str, resolution: HumanResolution
    ) -> ResolutionResult:
        existing = self._db.execute(
            "SELECT * FROM review_resolutions WHERE idempotency_key = ?",
            (resolution.idempotency_key,),
        ).fetchone()
        if not existing or existing["case_id"] != case_id:
            raise ValueError("resolution must be persisted before completion")
        if existing["status"] == "resolved":
            return ResolutionResult(
                existing["resolution_id"], case_id, existing["action"], "resolved"
            )
        case = self._db.execute(
            "SELECT * FROM review_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        with self._db:
            self._db.execute(
                "UPDATE review_resolutions SET status = 'resolved' WHERE resolution_id = ?",
                (existing["resolution_id"],),
            )
            self._db.execute("UPDATE review_cases SET status = 'resolved' WHERE case_id = ?", (case_id,))
            if case["case_type"] == "admission" and resolution.action in {"accept", "reject"}:
                self._db.execute(
                    "INSERT INTO human_admission_outcomes VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        f"human-outcome-{existing['resolution_id']}",
                        case_id,
                        resolution.action,
                        existing["resolution_id"],
                        case["packet_json"],
                    ),
                )
        return ResolutionResult(existing["resolution_id"], case_id, resolution.action, "resolved")

    def mark_resolution_retryable(
        self, case_id: str, resolution: HumanResolution, error_code: str
    ) -> None:
        with self._db:
            self._db.execute(
                """UPDATE review_resolutions
                   SET status = 'retryable', payload_json = ?
                   WHERE case_id = ? AND idempotency_key = ?""",
                (
                    json.dumps(
                        {
                            **record_dict(resolution),
                            "downstream_error_code": error_code,
                        },
                        sort_keys=True,
                    ),
                    case_id,
                    resolution.idempotency_key,
                ),
            )
            self._db.execute(
                "UPDATE review_cases SET status = 'open' WHERE case_id = ?",
                (case_id,),
            )

    @staticmethod
    def resolution_id_for(case_id: str, resolution: HumanResolution) -> str:
        return f"resolution-{_stable_hash([case_id, resolution.idempotency_key, resolution.action])[:20]}"

    def list_open(self) -> List[ReviewCase]:
        return [self._case(row) for row in self._db.execute("SELECT * FROM review_cases WHERE status IN ('open', 'processing')")]

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
            CREATE TABLE IF NOT EXISTS taxonomy_decisions (
                decision_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
                decision TEXT NOT NULL, authority TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS taxonomy_release_evidence (
                version_id TEXT PRIMARY KEY, coverage_plan_id TEXT NOT NULL,
                reference_regression_id TEXT NOT NULL, policy_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS taxonomy_change_packages (
                package_id TEXT PRIMARY KEY, candidate_id TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Preserve legacy decisions when opening a database created before the
        # append-only taxonomy_decisions ledger was introduced.
        legacy_rows = self._db.execute(
            """SELECT candidate_id, decision, reason_codes_json
               FROM taxonomy_candidates
               WHERE NOT EXISTS (
                   SELECT 1 FROM taxonomy_decisions
                   WHERE taxonomy_decisions.candidate_id = taxonomy_candidates.candidate_id
               )"""
        ).fetchall()
        for legacy in legacy_rows:
            self._db.execute(
                "INSERT INTO taxonomy_decisions VALUES (?, ?, ?, 'legacy_migration', ?, CURRENT_TIMESTAMP)",
                (
                    f"taxonomy-decision-{_stable_hash([legacy['candidate_id'], 'legacy', legacy['decision']])[:20]}",
                    legacy["candidate_id"],
                    legacy["decision"],
                    legacy["reason_codes_json"],
                ),
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
        elif max(
            int(taxonomy_context.get("distinct_scouts", 0)),
            int(taxonomy_context.get("distinct_briefs", 0)),
        ) < 2:
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["support_not_independently_generated"]
        elif candidate.facet == "aspect" and (
            int(taxonomy_context.get("distinct_scenarios", 0)) < 3
            or int(taxonomy_context.get("distinct_perspectives", 0)) < 2
            or int(taxonomy_context.get("distinct_answer_spaces", 0)) < 2
        ):
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["insufficient_aspect_breadth"]
        elif candidate.facet == "perspective" and (
            int(taxonomy_context.get("distinct_aspects", 0)) < 3
            or int(taxonomy_context.get("distinct_scenarios", 0)) < 3
        ):
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["insufficient_perspective_breadth"]
        elif not taxonomy_context.get("specialists_passed") or not taxonomy_context.get("challenger_passed"):
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["taxonomy_evidence_uncertain"]
        elif int(taxonomy_context.get("shadow_agreement", 0)) < 2:
            decision, reasons = AdmissionDecision.HUMAN_REVIEW, ["shadow_classifier_disagreement"]
        elif candidate.proposed_operation in {"merge", "split", "deprecate"} or (
            candidate.proposed_operation == "rename"
            and candidate.affected_taxon_ids
            and not taxonomy_context.get("definition_unchanged")
        ):
            if not taxonomy_context.get("affected_reclassification_verified"):
                decision, reasons = AdmissionDecision.HUMAN_REVIEW, [
                    "affected_question_revalidation_required"
                ]
            else:
                reasons = [
                    "independent_support",
                    "specialists_passed",
                    "affected_reclassification_verified",
                ]
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
            self._db.execute(
                "INSERT INTO taxonomy_decisions VALUES (?, ?, ?, 'automatic', ?, CURRENT_TIMESTAMP)",
                (
                    f"taxonomy-decision-{_stable_hash([candidate.candidate_id, decision.value, reasons])[:20]}",
                    candidate.candidate_id,
                    decision.value,
                    json.dumps(reasons),
                ),
            )
        return TaxonomyDecision(candidate.candidate_id, decision, tuple(reasons))

    def release(
        self,
        candidate_taxonomy_version: Dict[str, Any],
        *,
        staged: bool = False,
    ) -> TaxonomyVersion:
        key = candidate_taxonomy_version["idempotency_key"]
        existing = self._db.execute("SELECT * FROM taxonomy_versions WHERE idempotency_key = ?", (key,)).fetchone()
        if existing:
            return self._version(existing)
        candidate_ids = sorted(set(candidate_taxonomy_version["candidate_ids"]))
        candidates = []
        for candidate_id in candidate_ids:
            row = self._db.execute("SELECT * FROM taxonomy_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            latest_decision = self._db.execute(
                """SELECT decision FROM taxonomy_decisions WHERE candidate_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (candidate_id,),
            ).fetchone()
            if not row or not latest_decision or latest_decision[0] != AdmissionDecision.ACCEPT.value:
                raise ValueError("taxonomy release contains an unaccepted candidate")
            candidates.append(row)
        base_taxa: Dict[str, Dict[str, Dict[str, Any]]] = {
            "aspect": {},
            "perspective": {},
        }
        base_candidate_ids: List[str] = []
        classification_projection: Dict[str, Dict[str, str]] = {}
        base_version_id = candidate_taxonomy_version.get("base_version_id")
        if base_version_id:
            base_row = self._db.execute(
                "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ? AND released = 1",
                (base_version_id,),
            ).fetchone()
            if not base_row:
                raise ValueError("taxonomy release base version is not released")
            base_manifest = json.loads(base_row[0])
            base_taxa = self._manifest_taxa(base_manifest)
            base_candidate_ids = base_manifest["candidate_ids"]
            classification_projection = dict(
                base_manifest.get("classification_projection", {})
            )
        taxa = {
            facet: {taxon_id: dict(record) for taxon_id, record in records.items()}
            for facet, records in base_taxa.items()
        }
        operations = []
        for row in candidates:
            candidate = json.loads(row["payload_json"])
            change_package = self._db.execute(
                "SELECT payload_json FROM taxonomy_change_packages WHERE candidate_id = ?",
                (candidate["candidate_id"],),
            ).fetchone()
            if change_package:
                candidate.update(json.loads(change_package[0]))
            facet = candidate["facet"]
            if facet not in taxa:
                raise ValueError("taxonomy candidate facet must be aspect or perspective")
            operation = candidate.get("proposed_operation", "add")
            affected = candidate.get("affected_taxon_ids", [])
            if operation != "add" and not affected:
                raise ValueError("non-add taxonomy operations require affected taxon IDs")
            high_impact = operation in {"merge", "split", "deprecate"} or (
                operation == "rename" and bool(affected)
            )
            affected_revisions = candidate.get("affected_revision_ids", [])
            semantic_change = operation in {"merge", "split", "deprecate"} or bool(
                candidate.get("material_definition_change", False)
            )
            if high_impact and (
                not change_package
                or set(candidate.get("reclassification_plan", {}))
                != set(affected_revisions)
                or (
                    bool(affected_revisions)
                    and semantic_change
                    and not candidate.get("revalidation_evidence_ids")
                )
            ):
                raise ValueError(
                    "high-impact taxonomy operations require complete affected-question revalidation"
                )
            missing = [taxon_id for taxon_id in affected if taxon_id not in taxa[facet]]
            if missing:
                raise ValueError("taxonomy operation references an unknown taxon")
            taxon_id = candidate["label"].strip().lower().replace(" ", "_")
            record = {
                "id": taxon_id,
                "label": candidate["label"],
                "definition": candidate["definition"],
                "aliases": sorted(set(candidate.get("aliases", []))),
                "positive_examples": candidate.get("positive_examples", []),
                "counterexamples": candidate.get("counterexamples", []),
                "exclusions": candidate.get("exclusions", []),
                "deprecated": False,
                "replaced_by": [],
            }
            result_taxon_ids = [taxon_id]
            if operation == "alias":
                target = taxa[facet][affected[0]]
                target["aliases"] = sorted(
                    set(target.get("aliases", []))
                    | {candidate["label"]}
                    | set(candidate.get("aliases", []))
                )
            elif operation == "rename":
                target = taxa[facet][affected[0]]
                target["aliases"] = sorted(set(target.get("aliases", [])) | {target["label"]})
                target["label"] = candidate["label"]
                target["definition"] = candidate["definition"]
            elif operation == "deprecate":
                for affected_id in affected:
                    taxa[facet][affected_id]["deprecated"] = True
                    taxa[facet][affected_id]["replaced_by"] = [taxon_id] if taxon_id != affected_id else []
                if taxon_id not in taxa[facet]:
                    taxa[facet][taxon_id] = record
            elif operation == "merge":
                taxa[facet][taxon_id] = record
                for affected_id in affected:
                    taxa[facet][affected_id]["deprecated"] = True
                    taxa[facet][affected_id]["replaced_by"] = [taxon_id]
                    taxa[facet][taxon_id]["aliases"] = sorted(
                        set(taxa[facet][taxon_id]["aliases"])
                        | {taxa[facet][affected_id]["label"]}
                    )
            elif operation == "split":
                replacements = candidate.get("replacement_taxa", [])
                if len(replacements) < 2:
                    raise ValueError("split requires at least two replacement taxa")
                result_taxon_ids = []
                for replacement in replacements:
                    replacement_id = (
                        replacement["label"].strip().lower().replace(" ", "_")
                    )
                    if replacement_id in taxa[facet] or replacement_id in result_taxon_ids:
                        raise ValueError("split replacement taxon IDs must be new and distinct")
                    result_taxon_ids.append(replacement_id)
                    taxa[facet][replacement_id] = {
                        "id": replacement_id,
                        "label": replacement["label"],
                        "definition": replacement["definition"],
                        "aliases": sorted(set(replacement.get("aliases", []))),
                        "positive_examples": [],
                        "counterexamples": [],
                        "exclusions": replacement.get("exclusions", []),
                        "deprecated": False,
                        "replaced_by": [],
                    }
                for affected_id in affected:
                    taxa[facet][affected_id]["deprecated"] = True
                    taxa[facet][affected_id]["replaced_by"] = result_taxon_ids
            elif operation == "add":
                if taxon_id in taxa[facet]:
                    raise ValueError("add operation duplicates an existing taxon ID")
                taxa[facet][taxon_id] = record
            else:
                raise ValueError("unsupported taxonomy operation")
            operations.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "operation": operation,
                    "facet": facet,
                    "affected_taxon_ids": affected,
                    "result_taxon_ids": result_taxon_ids,
                    "material_definition_change": bool(
                        candidate.get("material_definition_change", False)
                    ),
                }
            )
            for revision_id, target_taxon_id in candidate.get(
                "reclassification_plan", {}
            ).items():
                classification_projection.setdefault(revision_id, {})[
                    facet
                ] = target_taxon_id
        aspects = sorted(
            taxon_id for taxon_id, record in taxa["aspect"].items() if not record["deprecated"]
        )
        perspectives = sorted(
            taxon_id for taxon_id, record in taxa["perspective"].items() if not record["deprecated"]
        )
        for projected in classification_projection.values():
            for facet, taxon_id in projected.items():
                if taxon_id not in taxa[facet] or taxa[facet][taxon_id]["deprecated"]:
                    raise ValueError(
                        "taxonomy reclassification projection targets an inactive taxon"
                    )
        manifest = {
            "base_version_id": base_version_id,
            "candidate_ids": sorted(set(base_candidate_ids) | set(candidate_ids)),
            "aspects": aspects,
            "perspectives": perspectives,
            "taxa": taxa,
            "operations": operations,
            "classification_projection": classification_projection,
        }
        content_hash = _stable_hash(manifest)
        version_id = f"taxonomy-{content_hash[:16]}"
        with self._db:
            self._db.execute(
                "INSERT INTO taxonomy_versions VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    version_id,
                    key,
                    json.dumps(manifest, sort_keys=True),
                    content_hash,
                    int(not staged),
                ),
            )
        return TaxonomyVersion(
            version_id,
            tuple(aspects),
            tuple(perspectives),
            content_hash,
            not staged,
        )

    def activate_staged(
        self,
        version_id: str,
        coverage_plan_id: str,
        reference_regression_id: str,
        policy_versions: Dict[str, str],
    ) -> TaxonomyVersion:
        row = self._db.execute(
            "SELECT * FROM taxonomy_versions WHERE version_id = ?", (version_id,)
        ).fetchone()
        if not row:
            raise KeyError(version_id)
        plan = self._db.execute(
            "SELECT 1 FROM coverage_plans WHERE plan_id = ? AND taxonomy_version_id = ?",
            (coverage_plan_id, version_id),
        ).fetchone()
        regression = self._db.execute(
            """SELECT 1 FROM reference_regressions
               WHERE regression_id = ? AND policy_hash = ?
                 AND taxonomy_version_id = ? AND passed = 1""",
            (
                reference_regression_id,
                _stable_hash(policy_versions),
                version_id,
            ),
        ).fetchone()
        if not plan or not regression:
            raise ValueError(
                "taxonomy activation requires its complete Coverage Plan and exact-taxonomy Reference regression"
            )
        with self._db:
            self._db.execute(
                "UPDATE taxonomy_versions SET released = 1 WHERE version_id = ?",
                (version_id,),
            )
            self._db.execute(
                """INSERT OR IGNORE INTO taxonomy_release_evidence VALUES (
                       ?, ?, ?, ?, CURRENT_TIMESTAMP
                   )""",
                (
                    version_id,
                    coverage_plan_id,
                    reference_regression_id,
                    _stable_hash(policy_versions),
                ),
            )
        return self._version(row, released=True)

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
        aspect_taxa = {taxon: self._initial_taxon(taxon) for taxon in sorted(set(aspects))}
        perspective_taxa = {
            taxon: self._initial_taxon(taxon) for taxon in sorted(set(perspectives))
        }
        manifest = {
            "base_version_id": None,
            "candidate_ids": [],
            "aspects": sorted(aspect_taxa),
            "perspectives": sorted(perspective_taxa),
            "taxa": {"aspect": aspect_taxa, "perspective": perspective_taxa},
            "operations": [],
            "classification_projection": {},
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

    def version_record(
        self, version_id: str, *, allow_staged: bool = False
    ) -> TaxonomyVersion:
        row = self._db.execute(
            "SELECT * FROM taxonomy_versions WHERE version_id = ?"
            + ("" if allow_staged else " AND released = 1"),
            (version_id,),
        ).fetchone()
        if not row:
            raise KeyError(version_id)
        return self._version(row)

    def has_version(self, version_id: str) -> bool:
        return bool(
            self._db.execute(
                "SELECT 1 FROM taxonomy_versions WHERE version_id = ? AND released = 1",
                (version_id,),
            ).fetchone()
        )

    def definition_context(
        self, version_id: str, *, allow_staged: bool = False
    ) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ?"
            + ("" if allow_staged else " AND released = 1"),
            (version_id,),
        ).fetchone()
        if not row:
            raise KeyError(version_id)
        manifest = json.loads(row[0])
        taxa = self._manifest_taxa(manifest)
        return {
            "version_id": version_id,
            "aspects": [taxa["aspect"][taxon] for taxon in manifest["aspects"]],
            "perspectives": [taxa["perspective"][taxon] for taxon in manifest["perspectives"]],
            "classification_projection": manifest.get(
                "classification_projection", {}
            ),
        }

    def is_ancestor_or_same(self, older_version_id: str, newer_version_id: str) -> bool:
        """Return whether a question classified under older remains in newer's lineage."""
        current = newer_version_id
        seen = set()
        while current and current not in seen:
            if current == older_version_id:
                return True
            seen.add(current)
            row = self._db.execute(
                "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ? AND released = 1",
                (current,),
            ).fetchone()
            if not row:
                return False
            current = json.loads(row[0]).get("base_version_id")
        return False

    def project_revision_facets(
        self,
        version_id: str,
        revision_id: str,
        aspect_id: str,
        perspective_id: str,
    ) -> tuple[str, str]:
        manifest = self.manifest_record(version_id, allow_staged=True)
        projected = manifest.get("classification_projection", {}).get(
            revision_id, {}
        )
        return (
            projected.get("aspect", aspect_id),
            projected.get("perspective", perspective_id),
        )

    def manifest_record(
        self, version_id: str, *, allow_staged: bool = False
    ) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT manifest_json FROM taxonomy_versions WHERE version_id = ?"
            + ("" if allow_staged else " AND released = 1"),
            (version_id,),
        ).fetchone()
        if not row:
            raise KeyError(version_id)
        return json.loads(row[0])

    def resolve_human_candidate(self, candidate_id: str, action: str) -> TaxonomyDecision:
        if action not in {"accept", "reject"}:
            raise ValueError("taxonomy review supports accept or reject")
        row = self._db.execute(
            "SELECT candidate_id FROM taxonomy_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if not row:
            raise KeyError(candidate_id)
        decision = (
            AdmissionDecision.ACCEPT if action == "accept" else AdmissionDecision.REJECT
        )
        reasons = ["human_taxonomy_resolution"]
        decision_id = f"taxonomy-decision-{_stable_hash([candidate_id, 'human', action])[:20]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO taxonomy_decisions VALUES (?, ?, ?, 'human', ?, CURRENT_TIMESTAMP)",
                (decision_id, candidate_id, decision.value, json.dumps(reasons)),
            )
        return TaxonomyDecision(candidate_id, decision, tuple(reasons))

    def candidate_record(self, candidate_id: str) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT payload_json FROM taxonomy_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if not row:
            raise KeyError(candidate_id)
        return json.loads(row[0])

    def attach_verified_change_package(
        self, candidate_id: str, package: Dict[str, Any]
    ) -> str:
        self.candidate_record(candidate_id)
        affected = sorted(set(package.get("affected_revision_ids", [])))
        plan = package.get("reclassification_plan", {})
        evidence_ids = sorted(set(package.get("revalidation_evidence_ids", [])))
        if set(plan) != set(affected):
            raise ValueError("reclassification plan must cover every affected revision")
        if affected and not evidence_ids:
            raise ValueError("affected revisions require revalidation evidence")
        normalized = {
            "affected_revision_ids": affected,
            "reclassification_plan": plan,
            "revalidation_evidence_ids": evidence_ids,
            "material_definition_change": bool(
                package.get("material_definition_change", False)
            ),
        }
        package_id = f"taxonomy-change-{_stable_hash([candidate_id, normalized])[:20]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO taxonomy_change_packages VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (package_id, candidate_id, json.dumps(normalized, sort_keys=True)),
            )
        return package_id

    @staticmethod
    def _initial_taxon(taxon_id: str) -> Dict[str, Any]:
        return {
            "id": taxon_id,
            "label": taxon_id.replace("_", " "),
            "definition": taxon_id.replace("_", " "),
            "aliases": [],
            "positive_examples": [],
            "counterexamples": [],
            "exclusions": [],
            "deprecated": False,
            "replaced_by": [],
        }

    @classmethod
    def _manifest_taxa(cls, manifest: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if "taxa" in manifest:
            return manifest["taxa"]
        return {
            "aspect": {taxon: cls._initial_taxon(taxon) for taxon in manifest["aspects"]},
            "perspective": {
                taxon: cls._initial_taxon(taxon) for taxon in manifest["perspectives"]
            },
        }

    @staticmethod
    def _version(
        row: sqlite3.Row, released: Optional[bool] = None
    ) -> TaxonomyVersion:
        manifest = json.loads(row["manifest_json"])
        return TaxonomyVersion(
            row["version_id"],
            tuple(manifest["aspects"]),
            tuple(manifest["perspectives"]),
            row["content_hash"],
            bool(row["released"]) if released is None else released,
        )


class CoveragePlanner:
    """Versioned meaningful regions and deterministic gap ordering."""

    def __init__(
        self,
        database_path: Path | str,
        bank: QuestionBank,
        taxonomy: Optional[TaxonomyRegistry] = None,
        named_theme_ids: Iterable[str] = (),
    ) -> None:
        self._db = _connection(database_path)
        self._bank = bank
        self._taxonomy = taxonomy
        self._named_theme_ids = tuple(
            theme for theme in named_theme_ids if not theme.lower().startswith("random")
        )
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS coverage_plans (
                plan_id TEXT PRIMARY KEY, taxonomy_version_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coverage_reports (
                report_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, snapshot_id TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coverage_plan_drafts (
                draft_id TEXT PRIMARY KEY, taxonomy_version_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS completion_records (
                completion_record_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL,
                taxonomy_version_id TEXT NOT NULL, coverage_plan_id TEXT NOT NULL,
                policy_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                complete INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def record_completion(
        self,
        snapshot_id: str,
        taxonomy_version_id: str,
        coverage_plan_id: str,
        policy_versions: Dict[str, str],
        rounds: List[Dict[str, Any]],
        complete: bool,
    ) -> str:
        payload = {
            "snapshot_id": snapshot_id,
            "taxonomy_version_id": taxonomy_version_id,
            "coverage_plan_id": coverage_plan_id,
            "policy_versions": policy_versions,
            "rounds": rounds,
            "complete": complete,
        }
        record_id = f"completion-{_stable_hash(payload)[:20]}"
        with self._db:
            self._db.execute(
                """INSERT OR IGNORE INTO completion_records VALUES (
                       ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                   )""",
                (
                    record_id,
                    snapshot_id,
                    taxonomy_version_id,
                    coverage_plan_id,
                    _stable_hash(policy_versions),
                    json.dumps(payload, sort_keys=True),
                    int(complete),
                ),
            )
        return record_id

    def completion_record(
        self,
        record_id: str,
        snapshot_id: str,
        taxonomy_version_id: str,
        coverage_plan_id: str,
        policy_versions: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM completion_records WHERE completion_record_id = ?",
            (record_id,),
        ).fetchone()
        if not row:
            return None
        if (
            row["snapshot_id"] != snapshot_id
            or row["taxonomy_version_id"] != taxonomy_version_id
            or row["coverage_plan_id"] != coverage_plan_id
            or row["policy_hash"] != _stable_hash(policy_versions)
        ):
            return None
        return json.loads(row["payload_json"])

    def plan(self, taxonomy_version: Dict[str, Any]) -> CoveragePlan:
        regions = taxonomy_version.get("regions", [])
        if not all(isinstance(region, CoverageRegion) for region in regions):
            raise ValueError("coverage regions must be explicitly classified")
        if not regions:
            raise ValueError("a Coverage Plan cannot be empty")
        region_keys = [
            (
                region.theme_id,
                region.level.value,
                region.aspect_id,
                region.perspective_id,
            )
            for region in regions
        ]
        if len(region_keys) != len(set(region_keys)):
            raise ValueError("every Coverage Region combination must be classified once")
        if self._taxonomy is not None:
            version = self._taxonomy.manifest_record(
                taxonomy_version["version_id"], allow_staged=True
            )
            expected = {
                (theme, level.value, aspect, perspective)
                for theme in self._named_theme_ids
                for level in QuestionLevel
                for aspect in version["aspects"]
                for perspective in version["perspectives"]
            }
            if set(region_keys) != expected:
                raise ValueError(
                    "Coverage Plan must classify every Named Theme × Level × Aspect × Perspective combination"
                )
        payload = [record_dict(region) for region in regions]
        plan_id = f"coverage-{_stable_hash([taxonomy_version['version_id'], payload])[:16]}"
        plan = CoveragePlan(plan_id, taxonomy_version["version_id"], list(regions))
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO coverage_plans VALUES (?, ?, ?)",
                (plan_id, plan.taxonomy_version_id, json.dumps(record_dict(plan), sort_keys=True)),
            )
        return plan

    def save_draft(
        self,
        draft_id: str,
        taxonomy_version_id: str,
        region_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = {
            "draft_id": draft_id,
            "taxonomy_version_id": taxonomy_version_id,
            "regions": region_records,
        }
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO coverage_plan_drafts VALUES (?, ?, ?, 'human_review')",
                (draft_id, taxonomy_version_id, json.dumps(payload, sort_keys=True)),
            )
        return payload

    def resolve_draft_region(
        self, draft_id: str, region_id: str, kind: str
    ) -> Dict[str, Any]:
        resolved_kind = CoverageRegionKind(kind)
        row = self._db.execute(
            "SELECT payload_json, status FROM coverage_plan_drafts WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
        if not row:
            raise KeyError(draft_id)
        payload = json.loads(row["payload_json"])
        found = False
        for region in payload["regions"]:
            if region["region_id"] == region_id:
                region["kind"] = resolved_kind.value
                found = True
        if not found:
            raise KeyError(region_id)
        unresolved = [region for region in payload["regions"] if not region.get("kind")]
        if unresolved:
            with self._db:
                self._db.execute(
                    "UPDATE coverage_plan_drafts SET payload_json = ? WHERE draft_id = ?",
                    (json.dumps(payload, sort_keys=True), draft_id),
                )
            return {"status": "human_review", "remaining": len(unresolved)}
        regions = [
            CoverageRegion(
                region["region_id"],
                region["theme_id"],
                QuestionLevel(region["level"]),
                region["aspect_id"],
                region["perspective_id"],
                CoverageRegionKind(region["kind"]),
                int(region.get("minimum_distinct_scenarios", 3)),
            )
            for region in payload["regions"]
        ]
        plan = self.plan(
            {"version_id": payload["taxonomy_version_id"], "regions": regions}
        )
        with self._db:
            self._db.execute(
                "UPDATE coverage_plan_drafts SET payload_json = ?, status = 'planned' WHERE draft_id = ?",
                (json.dumps(payload, sort_keys=True), draft_id),
            )
        return {"status": "planned", "coverage_plan": record_dict(plan)}

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
            matching = []
            for revision in revisions:
                aspect_id, perspective_id = (
                    self._taxonomy.project_revision_facets(
                        raw["taxonomy_version_id"],
                        revision.revision_id,
                        revision.aspect_id,
                        revision.perspective_id,
                    )
                    if self._taxonomy is not None
                    else (revision.aspect_id, revision.perspective_id)
                )
                if (
                    (revision.lifecycle == "active" or include_staged)
                    and region["theme_id"] in revision.theme_memberships
                    and region["level"] == revision.level
                    and region["aspect_id"] == aspect_id
                    and region["perspective_id"] == perspective_id
                ):
                    matching.append(revision)
            counts[region["region_id"]] = len(matching)
            scenario_counts[region["region_id"]] = _semantic_scenario_count(matching)
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
        alerts = set(coverage_report.concentration_alerts)

        def priority(region_id: str):
            region = regions[region_id]
            count = coverage_report.region_counts.get(region_id, 0)
            scenario_count = coverage_report.scenario_counts.get(region_id, 0)
            concentrated = any(f"region:{region_id}:" in alert for alert in alerts)
            if count == 0:
                rank = 1
            elif scenario_count < int(region["minimum_distinct_scenarios"]):
                rank = 2
            elif concentrated:
                rank = 3
            else:
                rank = 4
            # Hash-based rotation avoids repeatedly preferring the same Theme or
            # facet when multiple gaps have the same policy priority.
            rotation = _stable_hash(
                [coverage_report.report_id, region["theme_id"], region["level"], region["aspect_id"], region["perspective_id"]]
            )
            return rank, scenario_count, rotation

        briefs = []
        for region_id in sorted(coverage_report.gaps, key=priority):
            region = regions[region_id]
            region = {
                **region,
                "gap_priority": priority(region_id)[0],
                "concentration_alerts": sorted(
                    alert for alert in alerts if f"region:{region_id}:" in alert
                ),
            }
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
                if not strategy.get("eligible", True):
                    return False
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
                taxonomy_version_id TEXT NOT NULL DEFAULT '',
                invocation_ids_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        regression_columns = {
            row["name"] for row in self._db.execute("PRAGMA table_info(reference_regressions)")
        }
        if "taxonomy_version_id" not in regression_columns:
            self._db.execute(
                "ALTER TABLE reference_regressions ADD COLUMN taxonomy_version_id TEXT NOT NULL DEFAULT ''"
            )
        if "invocation_ids_json" not in regression_columns:
            self._db.execute(
                "ALTER TABLE reference_regressions ADD COLUMN invocation_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def import_examples(self, examples: List[Dict[str, Any]], confirmed: bool = False) -> int:
        with self._db:
            for example in examples:
                if not example.get("example_id") or not example.get("question") or not example.get("expected_decision"):
                    raise ValueError("each Reference Example needs id, question, and expected_decision")
                if ("neighbor_question" in example) != (
                    "expected_semantic_repeat" in example
                ):
                    raise ValueError(
                        "relation Reference Examples require both neighbor_question and expected_semantic_repeat"
                    )
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

    def confirmed_examples(self) -> List[Dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self._db.execute(
                "SELECT payload_json FROM reference_examples WHERE confirmed = 1 ORDER BY example_id"
            )
        ]

    def record_regression(
        self,
        policy_versions: Dict[str, str],
        results: Dict[str, bool],
        taxonomy_version_id: str = "",
        invocation_ids: Optional[List[str]] = None,
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
        invocation_ids = sorted(set(invocation_ids or []))
        regression_id = f"reference-regression-{_stable_hash([policy_hash, taxonomy_version_id, results])[:20]}"
        with self._db:
            self._db.execute(
                """INSERT OR IGNORE INTO reference_regressions(
                       regression_id, policy_hash, result_json, passed,
                       taxonomy_version_id, invocation_ids_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    regression_id,
                    policy_hash,
                    json.dumps(results, sort_keys=True),
                    int(passed),
                    taxonomy_version_id,
                    json.dumps(invocation_ids),
                ),
            )
        return regression_id

    def latest_regression_passed(
        self, policy_versions: Dict[str, str], taxonomy_version_id: str = ""
    ) -> bool:
        return self.latest_regression_record(policy_versions, taxonomy_version_id) is not None

    def latest_regression_record(
        self, policy_versions: Dict[str, str], taxonomy_version_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            """SELECT regression_id, policy_hash, result_json, passed,
                      taxonomy_version_id, invocation_ids_json
               FROM reference_regressions WHERE policy_hash = ?
                 AND taxonomy_version_id = ?
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (_stable_hash(policy_versions), taxonomy_version_id),
        ).fetchone()
        if not row or not row["passed"]:
            return None
        return {
            "regression_id": row["regression_id"],
            "policy_hash": row["policy_hash"],
            "result_hash": _stable_hash(json.loads(row["result_json"])),
            "taxonomy_version_id": row["taxonomy_version_id"],
            "invocation_ids": json.loads(row["invocation_ids_json"]),
            "passed": True,
        }


class SpotCheckRegistry:
    """Immutable human ten-question checks for initial and major-change releases."""

    def __init__(self, database_path: Path | str) -> None:
        self._db = _connection(database_path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS release_spot_checks (
                spot_check_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                policy_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                passed INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def record(
        self,
        idempotency_key: str,
        policy_versions: Dict[str, str],
        spot_check: Dict[str, Any],
    ) -> str:
        existing = self._db.execute(
            "SELECT spot_check_id FROM release_spot_checks WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return existing[0]
        checks = list(spot_check.get("checks", []))
        candidate_revision_ids = sorted(set(spot_check.get("candidate_revision_ids", [])))
        if len(checks) != 10:
            raise ValueError("a release spot check requires exactly ten questions")
        if any(not check.get("revision_id") for check in checks):
            raise ValueError("every spot-check result needs a revision_id")
        checked_ids = [check["revision_id"] for check in checks]
        if len(set(checked_ids)) != 10:
            raise ValueError("spot-check questions must be distinct")
        if not candidate_revision_ids or not set(checked_ids).issubset(candidate_revision_ids):
            raise ValueError("spot check must identify its complete candidate revision set")
        if not spot_check.get("reviewer_id"):
            raise ValueError("spot check requires a reviewer pseudonym")
        if spot_check.get("selection_method") != "random" or not spot_check.get(
            "selection_seed"
        ):
            raise ValueError("spot check must record reproducible random selection")
        passed = all(check.get("passed") is True for check in checks)
        payload = {
            "policy_versions": policy_versions,
            "checks": checks,
            "reviewer_id": spot_check["reviewer_id"],
            "selection_method": "random",
            "selection_seed": spot_check["selection_seed"],
            "candidate_revision_ids": candidate_revision_ids,
            "candidate_revision_set_hash": _stable_hash(candidate_revision_ids),
            "result_hash": _stable_hash(checks),
        }
        spot_check_id = f"spot-check-{_stable_hash([idempotency_key, payload])[:20]}"
        with self._db:
            self._db.execute(
                "INSERT INTO release_spot_checks VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    spot_check_id,
                    idempotency_key,
                    _stable_hash(policy_versions),
                    json.dumps(payload, sort_keys=True),
                    int(passed),
                ),
            )
        return spot_check_id

    def passed_record(
        self,
        spot_check_id: str,
        policy_versions: Dict[str, str],
        revision_ids: Iterable[str],
    ) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM release_spot_checks WHERE spot_check_id = ?",
            (spot_check_id,),
        ).fetchone()
        if not row or not row["passed"] or row["policy_hash"] != _stable_hash(policy_versions):
            return None
        payload = json.loads(row["payload_json"])
        candidate_revision_ids = sorted(set(revision_ids))
        if payload.get("candidate_revision_set_hash") != _stable_hash(
            candidate_revision_ids
        ):
            return None
        return {
            "spot_check_id": spot_check_id,
            "result_hash": payload["result_hash"],
            "question_count": len(payload["checks"]),
            "reviewer_id": payload["reviewer_id"],
            "selection_seed": payload["selection_seed"],
            "candidate_revision_set_hash": payload["candidate_revision_set_hash"],
            "passed": True,
        }


class ReleaseModule:
    """Immutable candidates, release gates, atomic current pointer, and rollback."""

    def __init__(
        self,
        database_path: Path | str,
        bank: QuestionBank,
        taxonomy: TaxonomyRegistry,
        coverage: CoveragePlanner,
        references: ReferenceExampleRegistry,
        revalidator: Callable[[list, list, str, Dict[str, Any]], Dict[str, Any]],
        spot_checks: Optional[SpotCheckRegistry] = None,
    ) -> None:
        # Release manifests and the current pointer share the trusted bank DB so
        # publication and lifecycle activation commit atomically.
        self._db = _connection(bank.database_path)
        self._bank = bank
        self._taxonomy = taxonomy
        self._coverage = coverage
        self._references = references
        self._revalidator = revalidator
        self._spot_checks = spot_checks
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS release_candidates (
                candidate_snapshot_id TEXT PRIMARY KEY, bank_snapshot_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL, intent_json TEXT NOT NULL,
                release_content_hash TEXT NOT NULL, report_json TEXT,
                audit_manifest_json TEXT, audit_content_hash TEXT,
                published INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS releases (
                release_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS release_pointer (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1), snapshot_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS withdrawn_snapshots (
                snapshot_id TEXT PRIMARY KEY, reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {
            row["name"] for row in self._db.execute("PRAGMA table_info(release_candidates)")
        }
        if "audit_manifest_json" not in columns:
            self._db.execute("ALTER TABLE release_candidates ADD COLUMN audit_manifest_json TEXT")
        if "audit_content_hash" not in columns:
            self._db.execute("ALTER TABLE release_candidates ADD COLUMN audit_content_hash TEXT")
        if "created_at" not in columns:
            self._db.execute(
                "ALTER TABLE release_candidates ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
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
        requested = set(release_intent.revision_ids)
        retirements = set(release_intent.retirement_revision_ids)
        all_revisions = self._bank.list_revisions()
        by_revision = {revision.revision_id: revision for revision in all_revisions}
        unknown_retirements = retirements - set(by_revision)
        if unknown_retirements:
            raise ValueError("release intent contains unknown retirements")
        requested_question_ids = {
            by_revision[revision_id].question_id
            for revision_id in requested
            if revision_id in by_revision
        }
        retirements |= {
            revision.revision_id
            for revision in all_revisions
            if revision.lifecycle == "active"
            and revision.question_id in requested_question_ids
            and revision.revision_id not in requested
        }
        current_bank_snapshot = self.current_bank_snapshot_id()
        current_revision_ids = (
            set(self._bank.snapshot_record(current_bank_snapshot).revision_ids)
            if current_bank_snapshot
            else {
                revision.revision_id
                for revision in all_revisions
                if revision.lifecycle == "active"
            }
        )
        retained_active = {
            revision.revision_id
            for revision in all_revisions
            if revision.revision_id in current_revision_ids
            and revision.revision_id not in retirements
            and revision.question_id not in requested_question_ids
        }
        included_revision_ids = sorted(requested | retained_active)
        snapshot = self._bank.snapshot({"revision_ids": included_revision_ids})
        normalized_intent = record_dict(release_intent)
        normalized_intent["revision_ids"] = included_revision_ids
        normalized_intent["retirement_revision_ids"] = sorted(retirements)
        if not normalized_intent.get("completion_record_id"):
            normalized_intent["completion_record_id"] = self._coverage.record_completion(
                snapshot.snapshot_id,
                release_intent.taxonomy_version_id,
                release_intent.coverage_plan_id,
                release_intent.policy_versions,
                [],
                False,
            )
        intent_json = json.dumps(normalized_intent, sort_keys=True)
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
        if row["published"] and row["report_json"]:
            raw_report = json.loads(row["report_json"])
            return ReleaseReport(
                raw_report["snapshot_id"],
                raw_report["passed"],
                raw_report["gate_results"],
                tuple(raw_report["reason_codes"]),
            )
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
        revalidation = self._revalidator(
            revisions,
            packages,
            snapshot.snapshot_id,
            intent,
        )
        if "gates" in revalidation:
            revalidation_gates = revalidation["gates"]
            revalidation_record = {
                "invocation_ids": revalidation.get("invocation_ids", []),
                "evidence_hash": revalidation.get("evidence_hash", ""),
            }
        else:  # Backward-compatible deterministic test/fake adapter.
            revalidation_gates = revalidation
            revalidation_record = {
                "invocation_ids": [],
                "evidence_hash": _stable_hash(revalidation),
            }
        question_ids = [revision.question_id for revision in revisions]
        normalized_texts = [" ".join(revision.text.lower().split()) for revision in revisions]
        coverage_report = None
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
        reference_record = self._references.latest_regression_record(
            intent["policy_versions"], intent["taxonomy_version_id"]
        )
        taxonomy_context = self._taxonomy.definition_context(intent["taxonomy_version_id"])
        approved_aspects = {taxon["id"] for taxon in taxonomy_context["aspects"]}
        approved_perspectives = {taxon["id"] for taxon in taxonomy_context["perspectives"]}
        projected_facets = {
            revision.revision_id: self._taxonomy.project_revision_facets(
                intent["taxonomy_version_id"],
                revision.revision_id,
                revision.aspect_id,
                revision.perspective_id,
            )
            for revision in revisions
        }
        facet_triples = [
            (
                revision.semantic_scenario.strip().lower(),
                projected_facets[revision.revision_id][1],
                revision.answer_space.strip().lower(),
            )
            for revision in revisions
        ]
        package_taxonomies_compatible = all(
            self._taxonomy.is_ancestor_or_same(
                package["taxonomy_version_id"], intent["taxonomy_version_id"]
            )
            for package in packages
        )
        spot_check_record = (
            self._spot_checks.passed_record(
                intent.get("spot_check_id", ""),
                intent["policy_versions"],
                snapshot.revision_ids,
            )
            if self._spot_checks
            else (
                {"spot_check_id": None, "passed": True, "legacy_assertion": True}
                if intent["spot_check_passed"]
                else None
            )
        )
        major_change_types = {
            "quality_policy",
            "safety_policy",
            "admission_policy",
            "semantic_repeat_policy",
            "taxonomy_material_change",
            "evaluator_topology",
            "prompt_or_rubric",
            "model_configuration",
            "source_permission_policy",
        }
        previous_release = self.current_snapshot_id()
        derived_major_change = False
        if previous_release:
            previous_row = self._db.execute(
                """SELECT audit_manifest_json FROM release_candidates
                   WHERE candidate_snapshot_id = ?""",
                (previous_release,),
            ).fetchone()
            previous_manifest = (
                json.loads(previous_row[0]) if previous_row and previous_row[0] else {}
            )
            previous_policies = previous_manifest.get("policy_versions", {})
            major_policy_keys = {
                "quality",
                "safety",
                "admission",
                "semantic_detection",
                "theme_classification",
                "agent_configuration",
                "source_permission",
            }
            derived_major_change = any(
                previous_policies.get(key) != intent["policy_versions"].get(key)
                for key in major_policy_keys
            )
            taxonomy_changed = (
                previous_manifest.get("taxonomy_version_id")
                != intent["taxonomy_version_id"]
            )
            if taxonomy_changed:
                taxonomy_manifest = self._taxonomy.manifest_record(
                    intent["taxonomy_version_id"]
                )
                derived_major_change = derived_major_change or any(
                    operation.get("operation") in {"merge", "split", "deprecate"}
                    or operation.get("material_definition_change", False)
                    for operation in taxonomy_manifest.get("operations", [])
                )
        spot_check_required = (
            previous_release is None
            or derived_major_change
            or bool(major_change_types & set(intent.get("change_types", [])))
        )
        completion_record = self._coverage.completion_record(
            intent.get("completion_record_id", ""),
            snapshot.snapshot_id,
            intent["taxonomy_version_id"],
            intent["coverage_plan_id"],
            intent["policy_versions"],
        )
        gates = {
            "content_hash": rebuilt.content_hash == snapshot.content_hash,
            "revision_content_integrity": self._bank.verify_snapshot_content(
                snapshot.snapshot_id
            ),
            "release_manifest_hash": release_content_hash == row["release_content_hash"],
            "nonempty": bool(revisions),
            "no_retired": all(
                revision.lifecycle != "retired"
                or revision.revision_id
                in self._bank.current_release_revision_ids()
                for revision in revisions
            ),
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
            "scoped_revalidation": package_taxonomies_compatible
            and all(revalidation_gates.values()),
            "exact_text_distinctness": len(normalized_texts) == len(set(normalized_texts)),
            "semantic_facet_distinctness": len(facet_triples) == len(set(facet_triples)),
            "taxonomy": self._taxonomy.has_version(intent["taxonomy_version_id"]),
            "approved_taxonomy_references": all(
                projected_facets[revision.revision_id][0] in approved_aspects
                and projected_facets[revision.revision_id][1]
                in approved_perspectives
                for revision in revisions
            ),
            "coverage": coverage_ok,
            "index_equivalence": first_projection == second_projection,
            "reference_examples": reference_record is not None,
            "spot_check": (not spot_check_required) or spot_check_record is not None,
            "completion_record": completion_record is not None,
            "policy_versions": (
                intent["policy_versions"] == DEFAULT_POLICY_VERSIONS
            ),
            **revalidation_gates,
        }
        passed = all(gates.values())
        reasons = tuple(sorted(key for key, value in gates.items() if not value))
        report = ReleaseReport(candidate_snapshot_id, passed, gates, reasons)
        index_record = {
            "lexical_version": intent["policy_versions"].get("lexical_projection"),
            "vector_version": intent["policy_versions"].get("vector_projection"),
            "semantic_fingerprint_version": intent["policy_versions"].get(
                "semantic_fingerprint_projection"
            ),
            "projection_hash": _stable_hash(first_projection),
            "equivalent_rebuild": first_projection == second_projection,
        }
        audit_manifest = {
            "release_number": self._db.execute(
                "SELECT COUNT(*) + 1 FROM releases WHERE status = 'released'"
            ).fetchone()[0],
            "created_at": row["created_at"],
            "candidate_snapshot_id": candidate_snapshot_id,
            "bank_snapshot_id": snapshot.snapshot_id,
            "previous_release_snapshot_id": previous_release,
            "revision_ids": list(snapshot.revision_ids),
            "bank_content_hash": snapshot.content_hash,
            "taxonomy_version_id": intent["taxonomy_version_id"],
            "taxonomy_manifest_hash": _stable_hash(
                self._taxonomy.manifest_record(intent["taxonomy_version_id"])
            ),
            "taxonomy_classification_projection": {
                "version": "taxonomy-classification-projection-v1",
                "hash": _stable_hash(projected_facets),
                "facets_by_revision": projected_facets,
            },
            "coverage_plan_id": intent["coverage_plan_id"],
            "coverage_report": record_dict(coverage_report) if coverage_report else None,
            "coverage_projection_version": "coverage-projection-v1",
            "completion_status": completion_record,
            "policy_versions": intent["policy_versions"],
            "admission_packages": [
                {
                    "revision_id": revision.revision_id,
                    "evidence_id": package["evidence"]["evidence_id"],
                    "outcome_id": package["outcome"]["outcome_id"],
                    "theme_classification_id": package["theme_classification"]["classification_id"],
                    "theme_memberships": package["theme_classification"]["memberships"],
                }
                for revision, package in zip(revisions, packages, strict=True)
            ],
            "revalidation": revalidation_record,
            "reference_regression": reference_record,
            "spot_check": spot_check_record,
            "spot_check_required": spot_check_required,
            "derived_major_change": derived_major_change,
            "lifecycle_decisions": {
                "activate_revision_ids": list(snapshot.revision_ids),
                "retire_revision_ids": sorted(intent.get("retirement_revision_ids", [])),
            },
            "index": index_record,
            "release_report": record_dict(report),
        }
        audit_content_hash = _stable_hash(audit_manifest)
        with self._db:
            self._db.execute(
                """UPDATE release_candidates
                   SET report_json = ?, audit_manifest_json = ?, audit_content_hash = ?
                   WHERE candidate_snapshot_id = ?""",
                (
                    json.dumps(record_dict(report), sort_keys=True),
                    json.dumps(audit_manifest, sort_keys=True),
                    audit_content_hash,
                    candidate_snapshot_id,
                ),
            )
        return report

    def publish(self, candidate_snapshot_id: str) -> QuestionBankRelease:
        if self._db.execute(
            "SELECT 1 FROM withdrawn_snapshots WHERE snapshot_id = ?",
            (candidate_snapshot_id,),
        ).fetchone():
            raise ValueError("a withdrawn snapshot can never be republished")
        report = self.verify(candidate_snapshot_id)
        if not report.passed:
            raise ValueError(f"release gates failed: {', '.join(report.reason_codes)}")
        candidate = self._db.execute(
            "SELECT * FROM release_candidates WHERE candidate_snapshot_id = ?",
            (candidate_snapshot_id,),
        ).fetchone()
        intent = json.loads(candidate["intent_json"])
        self._bank.snapshot_record(candidate["bank_snapshot_id"])
        release_hash = candidate["audit_content_hash"]
        if not release_hash or not candidate["audit_manifest_json"]:
            raise ValueError("verified immutable audit manifest is required")
        release_id = f"bank-{release_hash[:16]}"
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if self._db.execute(
                "SELECT 1 FROM withdrawn_snapshots WHERE snapshot_id = ?",
                (candidate_snapshot_id,),
            ).fetchone():
                raise ValueError("a withdrawn snapshot can never be republished")
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
            self._bank.apply_release_lifecycle(
                self._db,
                candidate["bank_snapshot_id"],
                intent.get("retirement_revision_ids", []),
            )
        return QuestionBankRelease(release_id, candidate_snapshot_id, release_hash, "released")

    def rollback(self, snapshot_id: str) -> QuestionBankRelease:
        candidate = self._db.execute(
            "SELECT * FROM release_candidates WHERE candidate_snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if not candidate:
            raise ValueError("rollback target must be a previously released immutable snapshot")
        if self._db.execute(
            "SELECT 1 FROM withdrawn_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone():
            raise ValueError("cannot roll back to a withdrawn snapshot")
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
            self._db.execute("BEGIN IMMEDIATE")
            if self._db.execute(
                "SELECT 1 FROM withdrawn_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone():
                raise ValueError("cannot roll back to a withdrawn snapshot")
            self._db.execute(
                "INSERT INTO releases VALUES (?, ?, ?, 'rollback', CURRENT_TIMESTAMP)",
                (release_id, snapshot_id, prior[0]),
            )
            self._db.execute(
                "INSERT INTO release_pointer(singleton, snapshot_id) VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET snapshot_id = excluded.snapshot_id",
                (snapshot_id,),
            )
        return QuestionBankRelease(release_id, snapshot_id, prior[0], "rollback")

    def withdraw(self, snapshot_id: str, reason: str) -> QuestionBankRelease:
        if not reason.strip():
            raise ValueError("withdrawal requires a safety, consent, or rights reason")
        released = self._db.execute(
            """SELECT content_hash FROM releases
               WHERE snapshot_id = ? AND status = 'released'
               ORDER BY created_at DESC LIMIT 1""",
            (snapshot_id,),
        ).fetchone()
        if not released:
            raise ValueError("only a released snapshot can be withdrawn")
        fallback = self._db.execute(
            """SELECT releases.snapshot_id FROM releases
               LEFT JOIN withdrawn_snapshots withdrawn
                 ON withdrawn.snapshot_id = releases.snapshot_id
               WHERE releases.status = 'released'
                 AND releases.snapshot_id != ?
                 AND withdrawn.snapshot_id IS NULL
               ORDER BY releases.created_at DESC, releases.rowid DESC LIMIT 1""",
            (snapshot_id,),
        ).fetchone()
        event_id = f"withdrawal-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO withdrawn_snapshots VALUES (?, ?, CURRENT_TIMESTAMP)",
                (snapshot_id, reason.strip()),
            )
            self._db.execute(
                "INSERT INTO releases VALUES (?, ?, ?, 'withdrawn', CURRENT_TIMESTAMP)",
                (event_id, snapshot_id, released[0]),
            )
            if self.current_snapshot_id() == snapshot_id:
                if fallback:
                    self._db.execute(
                        "UPDATE release_pointer SET snapshot_id = ? WHERE singleton = 1",
                        (fallback[0],),
                    )
                else:
                    self._db.execute("DELETE FROM release_pointer WHERE singleton = 1")
        return QuestionBankRelease(event_id, snapshot_id, released[0], "withdrawn")

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

    def audit_manifest(self, candidate_snapshot_id: str) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT audit_manifest_json FROM release_candidates WHERE candidate_snapshot_id = ?",
            (candidate_snapshot_id,),
        ).fetchone()
        if not row or not row[0]:
            raise ValueError("candidate has not completed release verification")
        return json.loads(row[0])


class QuestionUsageSink:
    """Write-only, separate telemetry database with 90-day raw retention."""

    ALLOWED_TYPES = {"presented", "skipped", "edit_completed", "confirmed", "round_finished"}
    ALLOWED_ORIGINS = {"released_bank", "bank", "human_authored", "legacy_migration"}
    OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

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
        if event.origin not in self.ALLOWED_ORIGINS:
            raise ValueError("origin must be a typed, non-user-content value")
        opaque_fields = {
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "session_pseudonym": event.session_pseudonym,
            "snapshot_id": event.snapshot_id,
            "question_id": event.question_id,
            "revision_id": event.revision_id,
            "round_id": event.round_id,
            "presentation_id": event.presentation_id,
        }
        if any(not self.OPAQUE_ID.fullmatch(value) for value in opaque_fields.values()):
            raise ValueError("usage identifiers must be opaque IDs without user content")
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
