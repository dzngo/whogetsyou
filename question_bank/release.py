"""Provider-free Question Bank release verification and pointer lifecycle."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from question_bank.contracts import (
    ConfigurationManifest,
    ReleasePointerEvent,
    ReleaseReport,
    canonical_data,
    stable_hash,
)
from question_bank.regression import ReferenceFixture
from question_bank.semantic import (
    EmbeddingAdapter,
    normalize_question,
    pair_metrics,
    route_pair,
)
from question_bank.store import V2Store


class ReleaseModule:
    """Builds immutable snapshots, verifies locally, and changes one release pointer."""

    def __init__(
        self, root: Path, *, configuration: ConfigurationManifest, embedder: EmbeddingAdapter
    ) -> None:
        configuration.validate_content_address()
        self._store = V2Store(root)
        self._configuration = configuration
        self._embedder = embedder
        self._db = sqlite3.connect(self._store.path)
        self._db.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS questions (
                question_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS question_revisions (
                revision_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL REFERENCES questions(question_id),
                candidate_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                configuration_id TEXT NOT NULL,
                text TEXT NOT NULL,
                level TEXT NOT NULL,
                themes_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                status TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS regression_records (
                record_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                configuration_id TEXT NOT NULL,
                fixture_hash TEXT NOT NULL,
                passed INTEGER NOT NULL,
                signature TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_id, configuration_id, fixture_hash, signature)
            );
            CREATE TABLE IF NOT EXISTS spot_check_records (
                record_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                configuration_id TEXT NOT NULL,
                question_ids_json TEXT NOT NULL,
                passed INTEGER NOT NULL,
                signature TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_id, configuration_id, signature)
            );
            CREATE TABLE IF NOT EXISTS release_manifests (
                manifest_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS release_pointer_events (
                event_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE NOT NULL,
                action TEXT NOT NULL,
                snapshot_id TEXT,
                previous_snapshot_id TEXT,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS snapshot_commands (
                idempotency_key TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS question_revisions_no_update
            BEFORE UPDATE ON question_revisions BEGIN
                SELECT RAISE(ABORT, 'question revisions are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS question_revisions_no_delete
            BEFORE DELETE ON question_revisions BEGIN
                SELECT RAISE(ABORT, 'question revisions are immutable');
            END;
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
        self._store.close()

    def build_candidate_snapshot(
        self, campaign_run_id: str, *, idempotency_key: str
    ) -> str:
        campaign_run_ids: list[str] = []
        current: str | None = campaign_run_id
        input_snapshot_id: str | None = None
        while current:
            run = self._db.execute(
                "SELECT * FROM runs WHERE run_id = ?", (current,)
            ).fetchone()
            if not run:
                raise KeyError(current)
            request = json.loads(run["request_json"])
            if request.get("mode") != "production":
                raise ValueError("candidate snapshots can only be built from a production campaign")
            if str(run["configuration_id"]) != self._configuration.manifest_id:
                raise ValueError("production campaign configuration does not match release configuration")
            if input_snapshot_id is None:
                input_snapshot_id = str(run["snapshot_id"])
            elif str(run["snapshot_id"]) != input_snapshot_id:
                raise ValueError("production campaign changed its fixed input snapshot")
            campaign_run_ids.append(current)
            current = str(run["prior_run_id"]) if run["prior_run_id"] else None
        run_marks = ",".join("?" for _ in campaign_run_ids)
        rows = self._db.execute(
            f"""SELECT c.*, r.configuration_id FROM candidates c
               JOIN runs r ON r.run_id = c.run_id
               WHERE c.state = 'staged' AND r.configuration_id = ?
               AND r.run_id IN ({run_marks})
               AND r.status = 'completed'
               AND r.stop_reason IN ('batch_complete', 'review_complete')
               ORDER BY c.candidate_id""",
            (self._configuration.manifest_id, *campaign_run_ids),
        ).fetchall()
        revision_ids: list[str] = []
        revision_roots: list[tuple[str, str]] = []
        base_snapshot = self._db.execute(
            "SELECT revision_ids_json FROM snapshots WHERE snapshot_id = ?",
            (input_snapshot_id,),
        ).fetchone()
        if not base_snapshot:
            raise ValueError("production campaign input snapshot is unavailable")
        base_revision_ids = tuple(json.loads(base_snapshot[0]))
        if base_revision_ids:
            base_marks = ",".join("?" for _ in base_revision_ids)
            base_revisions = self._db.execute(
                f"SELECT revision_id, content_hash FROM question_revisions WHERE revision_id IN ({base_marks})",
                base_revision_ids,
            ).fetchall()
            if len(base_revisions) != len(base_revision_ids):
                raise ValueError("production campaign input snapshot is incomplete")
            revision_ids.extend(str(item["revision_id"]) for item in base_revisions)
            revision_roots.extend(
                (str(item["revision_id"]), str(item["content_hash"]))
                for item in base_revisions
            )
        with self._db:
            for row in rows:
                themes = json.loads(row["themes_json"]) if row["themes_json"] is not None else None
                if themes is None:
                    continue
                payload = {
                    "candidate_id": row["candidate_id"], "run_id": row["run_id"],
                    "configuration_id": row["configuration_id"], "text": row["text"],
                    "level": row["level"], "themes": themes,
                    "metadata": json.loads(row["metadata_json"]),
                    "provenance": {"strategy": row["strategy"], "source_permission": "original_model_output"},
                    "status": "current",
                }
                question_id = f"question-{stable_hash(normalize_question(row['text']))[:24]}"
                revision_id = f"revision-{stable_hash(payload)[:24]}"
                content_hash = stable_hash(payload)
                self._db.execute("INSERT OR IGNORE INTO questions(question_id) VALUES (?)", (question_id,))
                self._db.execute(
                    """INSERT OR IGNORE INTO question_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        revision_id, question_id, row["candidate_id"], row["run_id"],
                        row["configuration_id"], row["text"], row["level"],
                        json.dumps(themes), json.dumps(payload["metadata"], sort_keys=True),
                        json.dumps(payload["provenance"], sort_keys=True), "current", content_hash,
                    ),
                )
                revision_ids.append(revision_id)
                revision_roots.append((revision_id, content_hash))
            revision_ids.sort()
            revision_roots.sort()
            snapshot_hash = stable_hash(revision_roots)
            snapshot_id = f"snapshot-{snapshot_hash[:24]}"
            existing = self._db.execute(
                "SELECT snapshot_id, content_hash FROM snapshot_commands WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing and (
                str(existing["snapshot_id"]) != snapshot_id
                or str(existing["content_hash"]) != snapshot_hash
            ):
                raise ValueError("idempotency key was already used for different snapshot content")
            self._db.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, 'candidate')",
                (snapshot_id, json.dumps(revision_ids), snapshot_hash),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO snapshot_commands VALUES (?, ?, ?)",
                (idempotency_key, snapshot_id, snapshot_hash),
            )
        return snapshot_id

    def record_regression(
        self, snapshot_id: str, *, fixture_hash: str, passed: bool, signature: str
    ) -> str:
        if fixture_hash != ReferenceFixture.load_default().fixture_hash:
            raise ValueError("regression does not match the frozen twelve-case fixture")
        record_id = f"regression-{stable_hash([snapshot_id, self._configuration.manifest_id, fixture_hash, signature])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO regression_records VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (record_id, snapshot_id, self._configuration.manifest_id, fixture_hash, int(passed), signature),
            )
        return record_id

    def record_spot_check(
        self, snapshot_id: str, *, question_ids: tuple[str, ...], passed: bool, signature: str
    ) -> str:
        if tuple(question_ids) != self.select_spot_check(snapshot_id):
            raise ValueError("spot check must use the deterministic protected sample")
        record_id = f"spot-{stable_hash([snapshot_id, question_ids, signature])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO spot_check_records VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (record_id, snapshot_id, self._configuration.manifest_id, json.dumps(question_ids), int(passed), signature),
            )
        return record_id

    def select_spot_check(self, snapshot_id: str) -> tuple[str, ...]:
        snapshot = self._db.execute(
            "SELECT revision_ids_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if not snapshot:
            raise KeyError(snapshot_id)
        revision_ids = tuple(json.loads(snapshot[0]))
        if not revision_ids:
            return ()
        placeholders = ",".join("?" for _ in revision_ids)
        rows = self._db.execute(
            f"SELECT * FROM question_revisions WHERE revision_id IN ({placeholders}) ORDER BY revision_id",
            revision_ids,
        ).fetchall()
        run_ids = tuple(sorted({str(row["run_id"]) for row in rows}))
        reviewed = 0
        if run_ids:
            run_marks = ",".join("?" for _ in run_ids)
            reviewed = int(
                self._db.execute(
                    f"""SELECT COUNT(DISTINCT candidate_id) FROM review_cases
                        WHERE run_id IN ({run_marks})
                        AND review_kind IN ('semantic_uncertainty','quality_uncertainty','metadata_uncertainty')""",
                    run_ids,
                ).fetchone()[0]
            )
        sample_size = min(len(rows), max(4, 10 - reviewed))
        vectors = self._embedder.embed([str(row["text"]) for row in rows])
        risky_pairs: list[tuple[float, str, str]] = []
        for right_index in range(len(rows)):
            for left_index in range(right_index):
                metrics = pair_metrics(
                    rows[left_index]["text"],
                    rows[right_index]["text"],
                    vectors[left_index],
                    vectors[right_index],
                )
                risk = max(
                    metrics.embedding_cosine,
                    metrics.character_cosine,
                    metrics.token_jaccard,
                    metrics.token_containment,
                )
                risky_pairs.append(
                    (-risk, str(rows[left_index]["question_id"]), str(rows[right_index]["question_id"]))
                )
        risky_pairs.sort()
        selected: list[str] = []
        risk_target = sample_size // 2
        for _, left, right in risky_pairs:
            for question_id in (left, right):
                if question_id not in selected:
                    selected.append(question_id)
                    if len(selected) == risk_target:
                        break
            if len(selected) == risk_target:
                break
        groups: set[tuple[str, str]] = set()
        for row in rows:
            question_id = str(row["question_id"])
            provenance = json.loads(row["provenance_json"])
            group = (str(row["level"]), str(provenance.get("strategy", "")))
            if question_id not in selected and group not in groups:
                selected.append(question_id)
                groups.add(group)
                if len(selected) == sample_size:
                    break
        for row in rows:
            question_id = str(row["question_id"])
            if question_id not in selected:
                selected.append(question_id)
                if len(selected) == sample_size:
                    break
        return tuple(selected)

    def verify(self, snapshot_id: str) -> ReleaseReport:
        snapshot = self._db.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if not snapshot:
            raise KeyError(snapshot_id)
        revision_ids = tuple(json.loads(snapshot["revision_ids_json"]))
        rows = self._db.execute(
            f"SELECT * FROM question_revisions WHERE revision_id IN ({','.join('?' for _ in revision_ids)}) ORDER BY revision_id",
            revision_ids,
        ).fetchall() if revision_ids else []
        blockers: set[str] = set()
        if len(rows) < 200:
            blockers.add("minimum_question_count")
        if len(rows) != len(revision_ids):
            blockers.add("snapshot_revision_set_incomplete")
        revision_roots = []
        for row in rows:
            payload = {
                "candidate_id": row["candidate_id"],
                "run_id": row["run_id"],
                "configuration_id": row["configuration_id"],
                "text": row["text"],
                "level": row["level"],
                "themes": json.loads(row["themes_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "provenance": json.loads(row["provenance_json"]),
                "status": row["status"],
            }
            recomputed = stable_hash(payload)
            if recomputed != row["content_hash"]:
                blockers.add("revision_hash_mismatch")
            revision_roots.append((str(row["revision_id"]), recomputed))
        if stable_hash(sorted(revision_roots)) != snapshot["content_hash"]:
            blockers.add("snapshot_hash_mismatch")
        if (self._embedder.model_id, self._embedder.dimensions, self._embedder.checksum) != (
            self._configuration.embedding_model,
            self._configuration.embedding_dimensions,
            self._configuration.embedding_checksum,
        ):
            blockers.add("embedding_artifact_mismatch")
        normalized = [normalize_question(row["text"]) for row in rows]
        if len(normalized) != len(set(normalized)):
            blockers.add("normalized_duplicate")
        question_ids_all = [str(row["question_id"]) for row in rows]
        if len(question_ids_all) != len(set(question_ids_all)):
            blockers.add("multiple_current_revisions")
        metadata = [json.loads(row["metadata_json"]) for row in rows]
        run_ids = tuple(sorted({str(row["run_id"]) for row in rows}))
        for row in rows:
            if row["configuration_id"] != self._configuration.manifest_id:
                blockers.add("configuration_mismatch")
            if row["status"] != "current":
                blockers.add("noncurrent_revision")
            provenance = json.loads(row["provenance_json"])
            if provenance.get("source_permission") != "original_model_output":
                blockers.add("source_permission_missing")
        for run_id in run_ids:
            ledger = self._store.ledger_summary(run_id)
            exposure = (
                ledger.reconciled_usd + ledger.active_reserved_usd + ledger.unknown_usd
            )
            if (
                exposure > ledger.authorized_usd
                or ledger.active_reserved_usd
                or ledger.unknown_usd
            ):
                blockers.add("ledger_not_release_safe")
        if run_ids:
            run_marks = ",".join("?" for _ in run_ids)
            open_admission = self._db.execute(
                f"""SELECT 1 FROM review_cases WHERE run_id IN ({run_marks})
                    AND status = 'open'
                    AND review_kind IN ('semantic_uncertainty','quality_uncertainty') LIMIT 1""",
                run_ids,
            ).fetchone()
            if open_admission:
                blockers.add("open_admission_review")
        for field in ("aspect", "perspective", "answer_space", "wording"):
            resolved = [item[field] for item in metadata if item.get(field) is not None]
            if rows and len(resolved) / len(rows) < 0.90:
                blockers.add(f"metadata_incomplete:{field}")
            limits = {"aspect": .20, "perspective": .30, "answer_space": .20, "wording": .25}
            if resolved and max(Counter(resolved).values()) / len(resolved) > limits[field] + 1e-12:
                blockers.add(f"diversity_collapse:{field}")
        for row in rows:
            evidence_rows = tuple(
                self._db.execute(
                    "SELECT evidence_type, payload_json FROM evidence WHERE run_id = ? AND candidate_id = ? AND configuration_id = ?",
                    (row["run_id"], row["candidate_id"], self._configuration.manifest_id),
                )
            )
            evidence = {
                item[0]
                for item in evidence_rows
            }
            quality_passed = any(
                item[0] in {"quality", "human_quality_resolution"}
                and json.loads(item[1]).get("deterministic_outcome") == "pass"
                for item in evidence_rows
            )
            if not quality_passed:
                blockers.add("missing_accepted_quality_evidence")
            if not (
                {"semantic_gate", "semantic_relation", "human_semantic_resolution"}
                & evidence
            ):
                blockers.add("missing_semantic_evidence")
        if rows and "embedding_artifact_mismatch" not in blockers:
            vectors = self._embedder.embed([row["text"] for row in rows])
            distinct_pairs: set[frozenset[str]] = set()
            for evidence_row in self._db.execute(
                "SELECT evidence_type, candidate_id, payload_json FROM evidence WHERE evidence_type IN ('semantic_relation', 'human_semantic_resolution') AND configuration_id = ?",
                (self._configuration.manifest_id,),
            ):
                payload = json.loads(evidence_row[2])
                if (
                    evidence_row[0] == "semantic_relation"
                    and payload.get("deterministic_outcome") == "distinct"
                ):
                    candidate_id = payload.get("candidate_id")
                    neighbor_id = payload.get("neighbor_id")
                    if isinstance(candidate_id, str) and isinstance(neighbor_id, str):
                        distinct_pairs.add(frozenset((candidate_id, neighbor_id)))
                elif (
                    evidence_row[0] == "human_semantic_resolution"
                    and payload.get("deterministic_outcome") == "pass"
                ):
                    for neighbor_id in payload.get("neighbor_ids", []):
                        if isinstance(neighbor_id, str):
                            distinct_pairs.add(
                                frozenset((str(evidence_row[1]), neighbor_id))
                            )
            for index, row in enumerate(rows):
                for prior_index in range(index):
                    metrics = pair_metrics(
                        row["text"],
                        rows[prior_index]["text"],
                        vectors[index],
                        vectors[prior_index],
                    )
                    route = route_pair(
                        row["text"], rows[prior_index]["text"], metrics
                    )
                    if route == "local_reject":
                        blockers.add("semantic_near_copy")
                        break
                    requires_relation = route == "gpt_review" or (
                        route == "local_distance"
                        and not self._configuration.local_distance_authority
                    )
                    relation_key = frozenset(
                        (
                            str(row["candidate_id"]),
                            str(rows[prior_index]["candidate_id"]),
                        )
                    )
                    if requires_relation and relation_key not in distinct_pairs:
                        blockers.add("missing_pair_distinct_evidence")
                        break
        regression = self._db.execute(
            "SELECT 1 FROM regression_records WHERE snapshot_id = ? AND configuration_id = ? AND fixture_hash = ? AND passed = 1",
            (snapshot_id, self._configuration.manifest_id, ReferenceFixture.load_default().fixture_hash),
        ).fetchone()
        spot = self._db.execute(
            "SELECT question_ids_json FROM spot_check_records WHERE snapshot_id = ? AND configuration_id = ? AND passed = 1",
            (snapshot_id, self._configuration.manifest_id),
        ).fetchone()
        if not regression:
            blockers.add("missing_regression")
        if not spot:
            blockers.add("missing_spot_check")
        elif tuple(json.loads(spot[0])) != self.select_spot_check(snapshot_id):
            blockers.add("spot_check_sample_mismatch")
        question_ids = tuple(str(row["question_id"]) for row in rows)
        ordered = tuple(sorted(blockers))
        evidence_roots = tuple(
            sorted(
                (str(item["evidence_id"]), stable_hash(json.loads(item["payload_json"])))
                for item in self._db.execute(
                    f"SELECT * FROM evidence WHERE run_id IN ({','.join('?' for _ in run_ids)})",
                    run_ids,
                )
            )
        ) if run_ids else ()
        ledger_roots = tuple(
            sorted(
                (str(item["reservation_id"]), str(item["state"]), int(item["actual_microusd"]))
                for item in self._db.execute(
                    f"SELECT * FROM ledger_entries WHERE run_id IN ({','.join('?' for _ in run_ids)})",
                    run_ids,
                )
            )
        ) if run_ids else ()
        invocation_roots = tuple(
            sorted(
                (
                    str(item["invocation_id"]),
                    str(item["role"]),
                    str(item["input_hash"]),
                    str(item["requested_model"]),
                    str(item["reported_model"]),
                    str(item["response_id"]),
                    str(item["status"]),
                    stable_hash(json.loads(item["output_json"])),
                    stable_hash(json.loads(item["usage_json"])),
                )
                for item in self._db.execute(
                    f"SELECT * FROM provider_invocations WHERE run_id IN ({','.join('?' for _ in run_ids)})",
                    run_ids,
                )
            )
        ) if run_ids else ()
        regression_roots = tuple(
            sorted(
                (str(item["record_id"]), str(item["fixture_hash"]), str(item["signature"]))
                for item in self._db.execute(
                    "SELECT * FROM regression_records WHERE snapshot_id = ? AND configuration_id = ? AND passed = 1",
                    (snapshot_id, self._configuration.manifest_id),
                )
            )
        )
        spot_roots = tuple(
            sorted(
                (
                    str(item["record_id"]),
                    tuple(json.loads(item["question_ids_json"])),
                    str(item["signature"]),
                )
                for item in self._db.execute(
                    "SELECT * FROM spot_check_records WHERE snapshot_id = ? AND configuration_id = ? AND passed = 1",
                    (snapshot_id, self._configuration.manifest_id),
                )
            )
        )
        manifest_hash = stable_hash(
            {
                "snapshot": snapshot_id,
                "configuration": canonical_data(self._configuration),
                "revisions": sorted(revision_roots),
                "evidence": evidence_roots,
                "ledger": ledger_roots,
                "invocations": invocation_roots,
                "regression": regression_roots,
                "spot_check": spot_roots,
                "metadata_distribution": {
                    field: sorted(Counter(item.get(field) for item in metadata).items(), key=str)
                    for field in ("aspect", "perspective", "answer_space", "wording")
                },
                "blockers": ordered,
            }
        )
        return ReleaseReport(snapshot_id, not ordered, ordered, question_ids, manifest_hash)

    def _current_snapshot(self) -> str | None:
        row = self._db.execute(
            "SELECT snapshot_id FROM release_pointer_events ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row and row[0] is not None else None

    def _event(self, action: str, snapshot_id: str | None, idempotency_key: str, reason: str = "") -> ReleasePointerEvent:
        existing = self._db.execute(
            "SELECT * FROM release_pointer_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            if (
                str(existing["action"]) != action
                or existing["snapshot_id"] != snapshot_id
                or str(existing["reason"]) != reason
            ):
                raise ValueError("idempotency key was already used for a different release action")
            return ReleasePointerEvent(
                existing["event_id"], existing["action"],
                existing["snapshot_id"], existing["previous_snapshot_id"],
            )
        previous = self._current_snapshot()
        event_id = f"release-event-{stable_hash([action, snapshot_id, idempotency_key])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT INTO release_pointer_events VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, idempotency_key, action, snapshot_id, previous, reason),
            )
        return ReleasePointerEvent(event_id, action, snapshot_id, previous)

    def publish(self, snapshot_id: str, *, idempotency_key: str) -> ReleasePointerEvent:
        existing = self._db.execute(
            "SELECT * FROM release_pointer_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            if str(existing["action"]) != "publish" or existing["snapshot_id"] != snapshot_id:
                raise ValueError("idempotency key was already used for a different release action")
            return ReleasePointerEvent(
                existing["event_id"], existing["action"],
                existing["snapshot_id"], existing["previous_snapshot_id"],
            )
        report = self.verify(snapshot_id)
        if not report.passed:
            raise ValueError(f"release blocked: {', '.join(report.blockers)}")
        manifest_id = f"release-{report.manifest_hash[:24]}"
        previous = self._current_snapshot()
        event_id = f"release-event-{stable_hash(['publish', snapshot_id, idempotency_key])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO release_manifests VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    manifest_id,
                    snapshot_id,
                    json.dumps(
                        {
                            "report": canonical_data(report),
                            "configuration": canonical_data(self._configuration),
                            "revision_ids": sorted(
                                json.loads(
                                    self._db.execute(
                                        "SELECT revision_ids_json FROM snapshots WHERE snapshot_id = ?",
                                        (snapshot_id,),
                                    ).fetchone()[0]
                                )
                            ),
                        },
                        sort_keys=True,
                    ),
                ),
            )
            self._db.execute("UPDATE snapshots SET status = 'released' WHERE snapshot_id = ?", (snapshot_id,))
            self._db.execute(
                "INSERT INTO release_pointer_events VALUES (?, ?, 'publish', ?, ?, '', CURRENT_TIMESTAMP)",
                (event_id, idempotency_key, snapshot_id, previous),
            )
        return ReleasePointerEvent(event_id, "publish", snapshot_id, previous)

    def withdraw(self, *, reason: str, idempotency_key: str) -> ReleasePointerEvent:
        if not reason.strip():
            raise ValueError("withdrawal reason is required")
        return self._event("withdraw", None, idempotency_key, reason)

    def rollback(self, snapshot_id: str, *, idempotency_key: str) -> ReleasePointerEvent:
        if not self.verify(snapshot_id).passed:
            raise ValueError("rollback target is no longer verifiable")
        return self._event("rollback", snapshot_id, idempotency_key)
