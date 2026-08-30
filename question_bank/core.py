"""Deterministic admission and trusted Question Bank state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from question_bank.contracts import (
    AcceptedQuestionPackage,
    AdmissionDecision,
    AdmissionOutcome,
    EvaluationEvidence,
    LifecycleRecord,
    QuestionBankSnapshot,
    QuestionProposal,
    QuestionRevision,
    record_dict,
)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AdmissionDecider:
    """Fail-closed rules; LLM votes never directly create admission authority."""

    def decide(self, proposal: QuestionProposal, evidence: EvaluationEvidence) -> AdmissionOutcome:
        reasons = []
        if proposal.source_permission not in {"de_novo", "internal_licensed", "human_authored"}:
            return self._outcome(proposal, evidence, AdmissionDecision.REJECT, ["source_permission_denied"])
        if evidence.hard_gate_failures or evidence.semantic_repeat:
            reasons = list(evidence.hard_gate_failures)
            if evidence.semantic_repeat:
                reasons.append("semantic_repeat")
            return self._outcome(proposal, evidence, AdmissionDecision.REJECT, reasons)
        if not evidence.complete:
            reasons.append("missing_evidence")
        if evidence.uncertainties:
            reasons.extend(evidence.uncertainties)
        if reasons:
            return self._outcome(proposal, evidence, AdmissionDecision.HUMAN_REVIEW, reasons)
        return self._outcome(
            proposal,
            evidence,
            AdmissionDecision.ACCEPT,
            ["all_hard_gates_pass", "globally_distinct"],
        )

    @staticmethod
    def _outcome(
        proposal: QuestionProposal,
        evidence: EvaluationEvidence,
        decision: AdmissionDecision,
        reasons: list[str],
    ) -> AdmissionOutcome:
        seed = [proposal.proposal_id, evidence.evidence_id, decision.value, sorted(reasons)]
        return AdmissionOutcome(
            outcome_id=f"outcome-{_stable_hash(seed)[:20]}",
            proposal_id=proposal.proposal_id,
            decision=decision,
            authority="automatic",
            evidence_id=evidence.evidence_id,
            reason_codes=reasons,
        )


class QuestionBank:
    """Owns stable question identity, immutable revisions, lifecycle, and snapshots."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS questions (
                question_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS question_revisions (
                revision_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL REFERENCES questions(question_id),
                revision_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                level TEXT NOT NULL,
                themes_json TEXT NOT NULL,
                aspect_id TEXT NOT NULL,
                perspective_id TEXT NOT NULL,
                semantic_scenario TEXT NOT NULL,
                answer_space TEXT NOT NULL,
                wording_pattern TEXT NOT NULL,
                lifecycle TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                taxonomy_version_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                UNIQUE(question_id, revision_number)
            );
            CREATE TABLE IF NOT EXISTS lifecycle_events (
                event_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS admission_packages (
                revision_id TEXT PRIMARY KEY, package_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS command_results (
                command_key TEXT PRIMARY KEY,
                command_type TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._connection.commit()

    def admit(self, package: AcceptedQuestionPackage) -> QuestionRevision:
        return self._write_revision(None, package, "admit")

    def revise(self, question_id: str, package: AcceptedQuestionPackage) -> QuestionRevision:
        return self._write_revision(question_id, package, "revise")

    def _write_revision(
        self,
        question_id: Optional[str],
        package: AcceptedQuestionPackage,
        command_type: str,
    ) -> QuestionRevision:
        self._validate_package(package)
        existing = self._command_result(package.idempotency_key)
        if existing:
            return self._row_to_revision(existing)
        with self._connection:
            if question_id is None:
                question_id = f"q-{uuid.uuid4().hex}"
                self._connection.execute("INSERT INTO questions(question_id) VALUES (?)", (question_id,))
                revision_number = 1
            else:
                found = self._connection.execute(
                    "SELECT 1 FROM questions WHERE question_id = ?", (question_id,)
                ).fetchone()
                if not found:
                    raise KeyError(f"Unknown question_id: {question_id}")
                revision_number = int(
                    self._connection.execute(
                        "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM question_revisions WHERE question_id = ?",
                        (question_id,),
                    ).fetchone()[0]
                )
            revision_id = f"qr-{uuid.uuid4().hex}"
            revision = QuestionRevision(
                question_id=question_id,
                revision_id=revision_id,
                revision_number=revision_number,
                text=package.proposal.text.strip(),
                level=package.proposal.level.value,
                theme_memberships=tuple(sorted(set(package.theme_classification.memberships))),
                aspect_id=package.evidence.resolved_facets["aspect_id"],
                perspective_id=package.evidence.resolved_facets["perspective_id"],
                semantic_scenario=package.evidence.resolved_facets["semantic_scenario"],
                answer_space=package.evidence.resolved_facets["answer_space"],
                wording_pattern=package.evidence.resolved_facets["wording_pattern"],
                lifecycle="staged",
                evidence_id=package.evidence.evidence_id,
                provenance=package.proposal.provenance,
            )
            content_hash = _stable_hash(record_dict(revision))
            self._connection.execute(
                """INSERT INTO question_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    revision.revision_id,
                    revision.question_id,
                    revision.revision_number,
                    revision.text,
                    revision.level,
                    json.dumps(revision.theme_memberships),
                    revision.aspect_id,
                    revision.perspective_id,
                    revision.semantic_scenario,
                    revision.answer_space,
                    revision.wording_pattern,
                    revision.lifecycle,
                    revision.evidence_id,
                    package.proposal.proposal_id,
                    json.dumps(revision.provenance, sort_keys=True),
                    package.taxonomy_version_id,
                    content_hash,
                ),
            )
            self._connection.execute(
                "INSERT INTO admission_packages VALUES (?, ?)",
                (
                    revision.revision_id,
                    json.dumps(record_dict(package), sort_keys=True),
                ),
            )
            event_id = f"life-{uuid.uuid4().hex}"
            self._connection.execute(
                "INSERT INTO lifecycle_events(event_id, question_id, revision_id, from_state, to_state, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, revision.question_id, revision.revision_id, None, "staged", "accepted_question_package"),
            )
            self._connection.execute(
                "INSERT INTO command_results VALUES (?, ?, ?)",
                (package.idempotency_key, command_type, json.dumps(record_dict(revision), sort_keys=True)),
            )
        return revision

    @staticmethod
    def _validate_package(package: AcceptedQuestionPackage) -> None:
        if package.outcome.decision != AdmissionDecision.ACCEPT:
            raise ValueError("final admission authority must be Accept")
        if package.outcome.evidence_id != package.evidence.evidence_id or not package.evidence.complete:
            raise ValueError("complete linked evaluation evidence is required")
        if package.outcome.proposal_id != package.proposal.proposal_id:
            raise ValueError("outcome and proposal do not match")
        if not package.theme_classification.resolved:
            raise ValueError("resolved theme classification is required")
        if package.theme_classification.proposal_id != package.proposal.proposal_id:
            raise ValueError("theme classification and proposal do not match")
        if "random" in {theme.lower() for theme in package.theme_classification.memberships}:
            raise ValueError("Random is not a stored theme membership")
        if not package.named_theme_ids:
            raise ValueError("current Named Theme definitions are required")
        unknown_themes = set(package.theme_classification.memberships) - set(
            package.named_theme_ids
        )
        if unknown_themes:
            raise ValueError("theme classification contains an unknown Named Theme")
        if not package.taxonomy_version_id or not package.proposal.aspect_id or not package.proposal.perspective_id:
            raise ValueError("approved taxonomy references are required")
        required_facets = {
            "aspect_id",
            "perspective_id",
            "semantic_scenario",
            "answer_space",
            "wording_pattern",
        }
        if set(package.evidence.resolved_facets) != required_facets:
            raise ValueError("complete evaluator-resolved facets are required")
        if not package.proposal.provenance:
            raise ValueError("provenance is required")
        if not package.policy_versions:
            raise ValueError("policy versions are required")

    def retire(self, question_id: str, retirement: Dict[str, str]) -> LifecycleRecord:
        key = retirement["idempotency_key"]
        existing = self._command_result(key)
        if existing:
            return LifecycleRecord(**existing)
        row = self._connection.execute(
            "SELECT * FROM question_revisions WHERE question_id = ? ORDER BY revision_number DESC LIMIT 1",
            (question_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Unknown question_id: {question_id}")
        event = LifecycleRecord(
            event_id=f"life-{uuid.uuid4().hex}",
            question_id=question_id,
            revision_id=row["revision_id"],
            from_state=row["lifecycle"],
            to_state="retired",
            reason=retirement["reason"],
        )
        with self._connection:
            self._connection.execute(
                "UPDATE question_revisions SET lifecycle = 'retired' WHERE question_id = ?",
                (question_id,),
            )
            self._connection.execute(
                "INSERT INTO lifecycle_events(event_id, question_id, revision_id, from_state, to_state, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (event.event_id, event.question_id, event.revision_id, event.from_state, event.to_state, event.reason),
            )
            self._connection.execute(
                "INSERT INTO command_results VALUES (?, 'retire', ?)", (key, json.dumps(record_dict(event)))
            )
        return event

    def snapshot(self, snapshot_selector: Dict[str, Iterable[str]]) -> QuestionBankSnapshot:
        revision_ids = tuple(sorted(set(snapshot_selector.get("revision_ids", []))))
        if revision_ids:
            placeholders = ",".join("?" for _ in revision_ids)
            rows = self._connection.execute(
                f"SELECT revision_id, content_hash, lifecycle FROM question_revisions WHERE revision_id IN ({placeholders})",
                revision_ids,
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT revision_id, content_hash, lifecycle FROM question_revisions WHERE lifecycle != 'retired'"
            ).fetchall()
            revision_ids = tuple(sorted(row["revision_id"] for row in rows))
        if len(rows) != len(revision_ids):
            raise ValueError("snapshot contains unknown revision")
        if any(row["lifecycle"] == "retired" for row in rows):
            raise ValueError("snapshot cannot contain retired revisions")
        if revision_ids:
            placeholders = ",".join("?" for _ in revision_ids)
            identities = self._connection.execute(
                f"SELECT question_id FROM question_revisions WHERE revision_id IN ({placeholders})",
                revision_ids,
            ).fetchall()
            if len({row["question_id"] for row in identities}) != len(identities):
                raise ValueError("snapshot may contain only one revision per Question ID")
        manifest = [(row["revision_id"], row["content_hash"]) for row in sorted(rows, key=lambda value: value["revision_id"])]
        content_hash = _stable_hash(manifest)
        snapshot_id = f"snapshot-{content_hash[:20]}"
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, 'candidate', CURRENT_TIMESTAMP)",
                (snapshot_id, json.dumps(manifest), content_hash),
            )
        return QuestionBankSnapshot(snapshot_id, revision_ids, content_hash)

    def list_revisions(self, snapshot_id: Optional[str] = None) -> list[QuestionRevision]:
        if snapshot_id:
            row = self._connection.execute(
                "SELECT manifest_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if not row:
                raise KeyError(snapshot_id)
            revision_ids = [item[0] for item in json.loads(row[0])]
            if not revision_ids:
                return []
            placeholders = ",".join("?" for _ in revision_ids)
            rows = self._connection.execute(
                f"SELECT * FROM question_revisions WHERE revision_id IN ({placeholders})", revision_ids
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM question_revisions").fetchall()
        return [self._row_to_revision(dict(row)) for row in rows]

    def set_snapshot_status(self, snapshot_id: str, status: str) -> None:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE snapshots SET status = ? WHERE snapshot_id = ?", (status, snapshot_id)
            )
            if not cursor.rowcount:
                raise KeyError(snapshot_id)
            if status == "released":
                manifest = self._connection.execute(
                    "SELECT manifest_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
                ).fetchone()[0]
                revision_ids = [item[0] for item in json.loads(manifest)]
                if revision_ids:
                    placeholders = ",".join("?" for _ in revision_ids)
                    self._connection.execute(
                        f"UPDATE question_revisions SET lifecycle = 'active' WHERE revision_id IN ({placeholders})",
                        revision_ids,
                    )

    def snapshot_record(self, snapshot_id: str) -> QuestionBankSnapshot:
        row = self._connection.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if not row:
            raise KeyError(snapshot_id)
        manifest = json.loads(row["manifest_json"])
        return QuestionBankSnapshot(row["snapshot_id"], tuple(item[0] for item in manifest), row["content_hash"], row["status"])

    def admission_package_record(self, revision_id: str) -> Dict[str, Any]:
        row = self._connection.execute(
            "SELECT package_json FROM admission_packages WHERE revision_id = ?",
            (revision_id,),
        ).fetchone()
        if not row:
            raise KeyError(revision_id)
        return json.loads(row[0])

    def _command_result(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._connection.execute("SELECT result_json FROM command_results WHERE command_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _row_to_revision(row: Dict[str, Any]) -> QuestionRevision:
        return QuestionRevision(
            question_id=row["question_id"],
            revision_id=row["revision_id"],
            revision_number=int(row["revision_number"]),
            text=row["text"],
            level=row["level"],
            theme_memberships=tuple(json.loads(row.get("themes_json", "[]"))) if "themes_json" in row else tuple(row["theme_memberships"]),
            aspect_id=row["aspect_id"],
            perspective_id=row["perspective_id"],
            semantic_scenario=row["semantic_scenario"],
            answer_space=row["answer_space"],
            wording_pattern=row["wording_pattern"],
            lifecycle=row["lifecycle"],
            evidence_id=row["evidence_id"],
            provenance=json.loads(row.get("provenance_json", "{}")) if "provenance_json" in row else row["provenance"],
        )
