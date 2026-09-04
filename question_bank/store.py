"""Transactional version-2 storage hidden behind the engine interface."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from decimal import Decimal
from pathlib import Path

from question_bank.contracts import (
    CandidateReport,
    CandidateState,
    ConfigurationManifest,
    LedgerSummary,
    Level,
    RunReport,
    RunRequest,
    canonical_data,
    money,
    stable_hash,
)

MICRO_USD = Decimal(1000000)


def _microusd(value: Decimal) -> int:
    return int((money(value) * MICRO_USD).to_integral_exact())


def _usd(value: int) -> Decimal:
    return money(Decimal(value) / MICRO_USD)


class V2Store:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "question_bank_v2.sqlite3"
        self._db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._initialize()

    def close(self) -> None:
        self._db.close()

    def _initialize(self) -> None:
        existing = {
            row[0]
            for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if existing and "schema_metadata" not in existing:
            raise ValueError("refusing to open a legacy schema as version-2 storage")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS configurations (
                configuration_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                revision_ids_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE NOT NULL,
                request_json TEXT NOT NULL,
                configuration_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                authorized_microusd INTEGER NOT NULL,
                attempt_limit INTEGER NOT NULL,
                status TEXT NOT NULL,
                stop_reason TEXT NOT NULL,
                report_json TEXT,
                prior_run_id TEXT,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ledger_entries (
                reservation_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                invocation_key TEXT NOT NULL,
                role TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                reserved_microusd INTEGER NOT NULL,
                actual_microusd INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL,
                usage_json TEXT NOT NULL DEFAULT '{}',
                error_code TEXT NOT NULL DEFAULT '',
                UNIQUE(run_id, invocation_key)
            );
            CREATE TABLE IF NOT EXISTS ledger_events (
                event_id TEXT PRIMARY KEY, reservation_id TEXT NOT NULL,
                run_id TEXT NOT NULL, event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS provider_invocations (
                invocation_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                reservation_id TEXT NOT NULL REFERENCES ledger_entries(reservation_id),
                role TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                output_json TEXT NOT NULL DEFAULT '{}',
                usage_json TEXT NOT NULL DEFAULT '{}',
                requested_model TEXT NOT NULL,
                reported_model TEXT NOT NULL DEFAULT '',
                response_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                error_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS application_cache (
                cache_key TEXT PRIMARY KEY,
                configuration_id TEXT NOT NULL,
                role TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                output_json TEXT NOT NULL,
                usage_json TEXT NOT NULL,
                reported_model TEXT NOT NULL,
                response_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                ordinal INTEGER NOT NULL,
                text TEXT NOT NULL,
                level TEXT NOT NULL,
                strategy TEXT NOT NULL,
                state TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL DEFAULT '[]',
                themes_json TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(run_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS candidate_outcomes (
                outcome_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL, state TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS metadata_classifications (
                classification_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL, themes_json TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_events (
                event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                status TEXT NOT NULL, stop_reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                candidate_id TEXT,
                evidence_type TEXT NOT NULL,
                configuration_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS review_cases (
                case_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                review_kind TEXT NOT NULL,
                priority INTEGER NOT NULL,
                packet_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, candidate_id)
            );
            CREATE TABLE IF NOT EXISTS review_resolutions (
                resolution_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES review_cases(case_id),
                idempotency_key TEXT UNIQUE NOT NULL,
                resolution_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS review_supplements (
                supplement_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES review_cases(case_id),
                idempotency_key TEXT UNIQUE NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        version = self._db.execute(
            "SELECT schema_version FROM schema_metadata WHERE singleton = 1"
        ).fetchone()
        if version and int(version[0]) != 2:
            raise ValueError(f"unsupported version-2 schema: {version[0]}")
        self._db.execute(
            "INSERT OR IGNORE INTO schema_metadata(singleton, schema_version) VALUES (1, 2)"
        )
        self._db.commit()

    def install_configuration(self, configuration: ConfigurationManifest) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO configurations VALUES (?, ?)",
                (
                    configuration.manifest_id,
                    json.dumps(canonical_data(configuration), sort_keys=True),
                ),
            )

    def ensure_empty_snapshot(self) -> str:
        content_hash = stable_hash([])
        snapshot_id = f"snapshot-{content_hash[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, '[]', ?, 'trusted')",
                (snapshot_id, content_hash),
            )
        return snapshot_id

    def snapshot_status(self, snapshot_id: str) -> str | None:
        row = self._db.execute(
            "SELECT status FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        return str(row[0]) if row else None

    def snapshot_questions(self, snapshot_id: str) -> tuple[tuple[str, str], ...]:
        snapshot = self._db.execute(
            "SELECT revision_ids_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if not snapshot:
            raise KeyError(snapshot_id)
        revision_ids = tuple(json.loads(snapshot[0]))
        if not revision_ids:
            return ()
        table = self._db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='question_revisions'"
        ).fetchone()
        if not table:
            raise ValueError("snapshot revisions are unavailable")
        placeholders = ",".join("?" for _ in revision_ids)
        rows = self._db.execute(
            f"SELECT question_id, text FROM question_revisions WHERE revision_id IN ({placeholders}) ORDER BY revision_id",
            revision_ids,
        ).fetchall()
        if len(rows) != len(revision_ids):
            raise ValueError("snapshot revision set is incomplete")
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def create_run(
        self, request: RunRequest, configuration_id: str, *, prior_run_id: str | None = None
    ) -> tuple[str, bool]:
        row = self._db.execute(
            "SELECT run_id FROM runs WHERE idempotency_key = ?", (request.idempotency_key,)
        ).fetchone()
        if row:
            return str(row["run_id"]), False
        run_id = f"run-{uuid.uuid4().hex}"
        with self._db:
            self._db.execute(
                """INSERT INTO runs(
                    run_id, idempotency_key, request_json, configuration_id, snapshot_id,
                    authorized_microusd, attempt_limit, status, stop_reason, prior_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', 'ready', ?)""",
                (
                    run_id,
                    request.idempotency_key,
                    json.dumps(canonical_data(request), sort_keys=True),
                    configuration_id,
                    request.snapshot_id,
                    _microusd(request.authorization_usd),
                    request.attempt_limit,
                    prior_run_id,
                ),
            )
        return run_id, True

    def run_row(self, run_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return row

    def set_run_state(self, run_id: str, status: str, stop_reason: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET status = ?, stop_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (status, stop_reason, run_id),
            )
            event_id = f"run-event-{uuid.uuid4().hex}"
            self._db.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, run_id, status, stop_reason),
            )

    def exposure_microusd(self, run_id: str) -> int:
        row = self._db.execute(
            """SELECT COALESCE(SUM(
                    CASE state
                        WHEN 'active' THEN reserved_microusd
                        WHEN 'unknown' THEN reserved_microusd
                        WHEN 'reconciled' THEN actual_microusd
                        ELSE 0
                    END
                ), 0) AS exposure
                FROM ledger_entries WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        exposure = int(row["exposure"])
        prior = self.run_row(run_id)["prior_run_id"]
        if prior:
            prior_totals = self._ledger_totals(str(prior))
            exposure += prior_totals[0] + prior_totals[1] + prior_totals[2]
        return exposure

    def _ledger_totals(self, run_id: str) -> tuple[int, int, int]:
        row = self._db.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN state = 'reconciled' THEN actual_microusd ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN state = 'active' THEN reserved_microusd ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN state = 'unknown' THEN reserved_microusd ELSE 0 END), 0)
                FROM ledger_entries WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        reconciled, active, unknown = (int(row[0]), int(row[1]), int(row[2]))
        prior = self.run_row(run_id)["prior_run_id"]
        if prior:
            prior_reconciled, prior_active, prior_unknown = self._ledger_totals(str(prior))
            reconciled += prior_reconciled
            active += prior_active
            unknown += prior_unknown
        return reconciled, active, unknown

    def recover_active_reservations(self, run_id: str) -> int:
        """Convert interrupted active calls to unknown spend before a continuation."""
        recovered = 0
        prior = self.run_row(run_id)["prior_run_id"]
        if prior:
            recovered += self.recover_active_reservations(str(prior))
        rows = self._db.execute(
            "SELECT reservation_id FROM ledger_entries WHERE run_id = ? AND state = 'active'",
            (run_id,),
        ).fetchall()
        with self._db:
            for row in rows:
                reservation_id = str(row[0])
                self._db.execute(
                    "UPDATE ledger_entries SET state = 'unknown', error_code = 'interrupted' WHERE reservation_id = ?",
                    (reservation_id,),
                )
                self._db.execute(
                    "UPDATE provider_invocations SET status = 'ambiguous_failure', error_code = 'interrupted' WHERE reservation_id = ?",
                    (reservation_id,),
                )
                self._db.execute(
                    "INSERT INTO ledger_events VALUES (?, ?, ?, 'unknown', ?, CURRENT_TIMESTAMP)",
                    (
                        f"ledger-event-{uuid.uuid4().hex}",
                        reservation_id,
                        run_id,
                        json.dumps({"error_code": "interrupted"}, sort_keys=True),
                    ),
                )
        return recovered + len(rows)

    def prior_unknown_invocation(self, run_id: str, *, role: str, input_hash: str) -> bool:
        prior = self.run_row(run_id)["prior_run_id"]
        while prior:
            found = self._db.execute(
                """SELECT 1 FROM provider_invocations p
                   JOIN ledger_entries l ON l.reservation_id = p.reservation_id
                   WHERE p.run_id = ? AND p.role = ? AND p.input_hash = ? AND l.state = 'unknown'""",
                (prior, role, input_hash),
            ).fetchone()
            if found:
                return True
            prior = self.run_row(str(prior))["prior_run_id"]
        return False

    def attempt_count(self, run_id: str) -> int:
        return int(
            self._db.execute(
                "SELECT COUNT(*) FROM ledger_entries WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        )

    def campaign_attempt_count(self, run_id: str) -> int:
        total = self.attempt_count(run_id)
        prior = self.run_row(run_id)["prior_run_id"]
        if prior:
            total += self.campaign_attempt_count(str(prior))
        return total

    def can_fit(self, run_id: str, reservation_usd: Decimal, attempts: int = 1) -> bool:
        row = self.run_row(run_id)
        return (
            self.exposure_microusd(run_id) + _microusd(reservation_usd)
            <= int(row["authorized_microusd"])
            and self.campaign_attempt_count(run_id) + attempts <= int(row["attempt_limit"])
        )

    def reserve(
        self,
        run_id: str,
        *,
        invocation_key: str,
        role: str,
        provider: str,
        model: str,
        reservation_usd: Decimal,
        input_hash: str,
    ) -> tuple[str, str] | None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT reservation_id FROM ledger_entries WHERE run_id = ? AND invocation_key = ?",
                    (run_id, invocation_key),
                ).fetchone()
                if existing:
                    self._db.rollback()
                    return None
                run = self.run_row(run_id)
                exposure = self.exposure_microusd(run_id)
                attempts = self.campaign_attempt_count(run_id)
                requested = _microusd(reservation_usd)
                if (
                    exposure + requested > int(run["authorized_microusd"])
                    or attempts + 1 > int(run["attempt_limit"])
                ):
                    self._db.rollback()
                    return None
                reservation_id = f"reservation-{uuid.uuid4().hex}"
                invocation_id = f"invocation-{uuid.uuid4().hex}"
                self._db.execute(
                    """INSERT INTO ledger_entries(
                        reservation_id, run_id, invocation_key, role, provider, model,
                        reserved_microusd, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (
                        reservation_id,
                        run_id,
                        invocation_key,
                        role,
                        provider,
                        model,
                        requested,
                    ),
                )
                self._db.execute(
                    "INSERT INTO ledger_events VALUES (?, ?, ?, 'reserved', ?, CURRENT_TIMESTAMP)",
                    (
                        f"ledger-event-{uuid.uuid4().hex}", reservation_id, run_id,
                        json.dumps({"reserved_microusd": requested}, sort_keys=True),
                    ),
                )
                self._db.execute(
                    """INSERT INTO provider_invocations(
                        invocation_id, run_id, reservation_id, role, input_hash,
                        requested_model, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active')""",
                    (
                        invocation_id,
                        run_id,
                        reservation_id,
                        role,
                        input_hash,
                        model,
                    ),
                )
                self._db.commit()
                return reservation_id, invocation_id
            except Exception:
                self._db.rollback()
                raise

    def reconcile(
        self,
        reservation_id: str,
        invocation_id: str,
        *,
        actual_usd: Decimal,
        output: dict,
        usage: dict,
        reported_model: str,
        response_id: str,
    ) -> None:
        with self._db:
            self._db.execute(
                """UPDATE ledger_entries
                    SET actual_microusd = ?, state = 'reconciled', usage_json = ?
                    WHERE reservation_id = ? AND state = 'active'""",
                (_microusd(actual_usd), json.dumps(usage, sort_keys=True), reservation_id),
            )
            self._db.execute(
                """UPDATE provider_invocations
                    SET output_json = ?, usage_json = ?, reported_model = ?, response_id = ?, status = 'succeeded'
                    WHERE invocation_id = ?""",
                (
                    json.dumps(output, sort_keys=True),
                    json.dumps(usage, sort_keys=True),
                    reported_model,
                    response_id,
                    invocation_id,
                ),
            )
            ledger = self._db.execute(
                "SELECT run_id FROM ledger_entries WHERE reservation_id = ?", (reservation_id,)
            ).fetchone()
            self._db.execute(
                "INSERT INTO ledger_events VALUES (?, ?, ?, 'reconciled', ?, CURRENT_TIMESTAMP)",
                (
                    f"ledger-event-{uuid.uuid4().hex}", reservation_id, ledger["run_id"],
                    json.dumps({"actual_microusd": _microusd(actual_usd), "usage": usage}, sort_keys=True),
                ),
            )
            invocation = self._db.execute(
                """SELECT p.role, p.input_hash, r.configuration_id
                   FROM provider_invocations p JOIN runs r ON r.run_id = p.run_id
                   WHERE p.invocation_id = ?""",
                (invocation_id,),
            ).fetchone()
            cache_key = stable_hash(
                [invocation["configuration_id"], invocation["role"], invocation["input_hash"]]
            )
            self._db.execute(
                """INSERT OR IGNORE INTO application_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    cache_key, invocation["configuration_id"], invocation["role"],
                    invocation["input_hash"], json.dumps(output, sort_keys=True),
                    json.dumps(usage, sort_keys=True), reported_model, response_id,
                ),
            )

    def cached_result(
        self, *, configuration_id: str, role: str, input_hash: str, run_id: str
    ):
        cache_key = stable_hash([configuration_id, role, input_hash])
        row = self._db.execute(
            "SELECT * FROM application_cache WHERE cache_key = ? AND configuration_id = ? AND role = ? AND input_hash = ?",
            (cache_key, configuration_id, role, input_hash),
        ).fetchone()
        if not row:
            return None
        from question_bank.contracts import ProviderResult, ProviderUsage

        usage = json.loads(row["usage_json"])
        with self._db:
            self._db.execute("UPDATE runs SET cache_hits = cache_hits + 1 WHERE run_id = ?", (run_id,))
        return ProviderResult(
            json.loads(row["output_json"]), ProviderUsage(**usage),
            str(row["reported_model"]), str(row["response_id"]),
        )

    def fail_invocation(
        self,
        reservation_id: str,
        invocation_id: str,
        *,
        error_code: str,
        ambiguous: bool,
    ) -> None:
        state = "unknown" if ambiguous else "released"
        with self._db:
            self._db.execute(
                "UPDATE ledger_entries SET state = ?, error_code = ? WHERE reservation_id = ? AND state = 'active'",
                (state, error_code, reservation_id),
            )
            self._db.execute(
                "UPDATE provider_invocations SET status = ?, error_code = ? WHERE invocation_id = ?",
                ("ambiguous_failure" if ambiguous else "definitive_failure", error_code, invocation_id),
            )
            ledger = self._db.execute(
                "SELECT run_id FROM ledger_entries WHERE reservation_id = ?", (reservation_id,)
            ).fetchone()
            self._db.execute(
                "INSERT INTO ledger_events VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    f"ledger-event-{uuid.uuid4().hex}", reservation_id, ledger["run_id"],
                    "unknown" if ambiguous else "released",
                    json.dumps({"error_code": error_code}, sort_keys=True),
                ),
            )

    def add_candidates(self, run_id: str, candidates: tuple[CandidateReport, ...]) -> None:
        with self._db:
            for ordinal, candidate in enumerate(candidates):
                self._db.execute(
                    """INSERT OR IGNORE INTO candidates(
                        candidate_id, run_id, ordinal, text, level, strategy, state,
                        reason_codes_json, themes_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        candidate.candidate_id,
                        run_id,
                        ordinal,
                        candidate.text,
                        candidate.level.value,
                        candidate.strategy,
                        candidate.state.value,
                        json.dumps(candidate.reason_codes),
                        (
                            json.dumps(candidate.theme_memberships)
                            if candidate.theme_memberships is not None
                            else None
                        ),
                        json.dumps(candidate.metadata, sort_keys=True),
                    ),
                )

    def set_candidate_state(
        self, run_id: str, state: CandidateState, reason_codes: tuple[str, ...]
    ) -> None:
        rows = self._db.execute(
            "SELECT candidate_id FROM candidates WHERE run_id = ? AND state = 'proposed'", (run_id,)
        ).fetchall()
        with self._db:
            self._db.execute(
                "UPDATE candidates SET state = ?, reason_codes_json = ? WHERE run_id = ? AND state = 'proposed'",
                (state.value, json.dumps(reason_codes), run_id),
            )
            for row in rows:
                self._insert_candidate_outcome(run_id, str(row[0]), state, reason_codes)

    def set_candidate_outcome(
        self,
        candidate_id: str,
        state: CandidateState,
        reason_codes: tuple[str, ...],
    ) -> None:
        row = self._db.execute(
            "SELECT run_id FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if not row:
            raise KeyError(candidate_id)
        with self._db:
            self._db.execute(
                "UPDATE candidates SET state = ?, reason_codes_json = ? WHERE candidate_id = ?",
                (state.value, json.dumps(reason_codes), candidate_id),
            )
            self._insert_candidate_outcome(str(row[0]), candidate_id, state, reason_codes)

    def _insert_candidate_outcome(
        self, run_id: str, candidate_id: str, state: CandidateState, reason_codes: tuple[str, ...]
    ) -> None:
        self._db.execute(
            "INSERT INTO candidate_outcomes VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (
                f"outcome-{uuid.uuid4().hex}", run_id, candidate_id,
                state.value, json.dumps(reason_codes),
            ),
        )

    def set_candidate_metadata(
        self,
        candidate_id: str,
        *,
        themes: tuple[str, ...] | None,
        metadata: dict,
    ) -> None:
        with self._db:
            self._db.execute(
                "UPDATE candidates SET themes_json = ?, metadata_json = ? WHERE candidate_id = ?",
                (
                    json.dumps(themes) if themes is not None else None,
                    json.dumps(metadata, sort_keys=True),
                    candidate_id,
                ),
            )
            run_id = self._db.execute(
                "SELECT run_id FROM candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()[0]
            classification_id = f"metadata-{stable_hash([run_id, candidate_id, themes, metadata])[:24]}"
            self._db.execute(
                "INSERT OR IGNORE INTO metadata_classifications VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    classification_id, run_id, candidate_id,
                    json.dumps(themes) if themes is not None else None,
                    json.dumps(metadata, sort_keys=True),
                ),
            )

    def open_review_case(
        self,
        *,
        run_id: str,
        candidate_id: str,
        review_kind: str,
        priority: int,
        packet: dict,
    ) -> str:
        case_id = f"review-{stable_hash([run_id, candidate_id])[:24]}"
        with self._db:
            self._db.execute(
                """INSERT OR IGNORE INTO review_cases(
                    case_id, run_id, candidate_id, review_kind, priority, packet_json
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    case_id,
                    run_id,
                    candidate_id,
                    review_kind,
                    priority,
                    json.dumps(packet, sort_keys=True),
                ),
            )
        return case_id

    def review_case_ids(self, run_id: str) -> tuple[str, ...]:
        rows = self._db.execute(
            "SELECT case_id FROM review_cases WHERE run_id = ? ORDER BY priority, created_at, case_id",
            (run_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def review_candidate_ids(self, run_id: str) -> tuple[str, ...]:
        rows = self._db.execute(
            "SELECT DISTINCT candidate_id FROM review_cases WHERE run_id = ? ORDER BY candidate_id",
            (run_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def semantic_risk_candidate_pairs(self, run_id: str) -> tuple[tuple[str, str], ...]:
        """Return locally distinct candidate pairs from highest to lowest similarity risk."""
        candidate_ids = {
            str(row[0])
            for row in self._db.execute(
                "SELECT candidate_id FROM candidates WHERE run_id = ?", (run_id,)
            )
        }
        ranked: list[tuple[float, str, str]] = []
        for row in self._db.execute(
            """SELECT payload_json FROM evidence
               WHERE run_id = ? AND evidence_type = 'local_semantic_pair'""",
            (run_id,),
        ):
            payload = json.loads(row[0])
            left = payload.get("candidate_id")
            right = payload.get("neighbor_id")
            if (
                payload.get("route") != "local_distance"
                or left not in candidate_ids
                or right not in candidate_ids
            ):
                continue
            risk = max(
                float(payload.get("embedding_cosine", 0.0)),
                float(payload.get("character_cosine", 0.0)),
                float(payload.get("token_jaccard", 0.0)),
                float(payload.get("token_containment", 0.0)),
            )
            ranked.append((-risk, str(left), str(right)))
        ranked.sort()
        return tuple((left, right) for _, left, right in ranked)

    def review_case(self, case_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM review_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if not row:
            raise KeyError(case_id)
        return {
            "case_id": str(row["case_id"]),
            "run_id": str(row["run_id"]),
            "candidate_id": str(row["candidate_id"]),
            "review_kind": str(row["review_kind"]),
            "priority": int(row["priority"]),
            "packet": json.loads(row["packet_json"]),
            "status": str(row["status"]),
        }

    def review_resolution_by_key(self, idempotency_key: str) -> dict | None:
        row = self._db.execute(
            "SELECT resolution_json FROM review_resolutions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def resolve_review_case(
        self,
        case_id: str,
        *,
        idempotency_key: str,
        resolution: dict,
        metadata_update: tuple[tuple[str, ...] | None, dict] | None = None,
    ) -> dict:
        existing = self.review_resolution_by_key(idempotency_key)
        if existing is not None:
            return existing
        case = self.review_case(case_id)
        if case["status"] != "open":
            raise ValueError("review case already resolved with another idempotency key")
        result = {**case, "status": "resolved", "resolution": resolution}
        resolution_id = f"resolution-{stable_hash([case_id, idempotency_key, resolution])[:24]}"
        with self._db:
            if metadata_update is not None:
                themes, metadata = metadata_update
                self._db.execute(
                    "UPDATE candidates SET themes_json = ?, metadata_json = ? WHERE candidate_id = ?",
                    (
                        json.dumps(themes) if themes is not None else None,
                        json.dumps(metadata, sort_keys=True),
                        case["candidate_id"],
                    ),
                )
                classification_id = f"metadata-{stable_hash([case['run_id'], case['candidate_id'], themes, metadata])[:24]}"
                self._db.execute(
                    "INSERT OR IGNORE INTO metadata_classifications VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        classification_id,
                        case["run_id"],
                        case["candidate_id"],
                        json.dumps(themes) if themes is not None else None,
                        json.dumps(metadata, sort_keys=True),
                    ),
                )
            self._db.execute(
                "INSERT INTO review_resolutions VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (resolution_id, case_id, idempotency_key, json.dumps(result, sort_keys=True)),
            )
            self._db.execute(
                "UPDATE review_cases SET status = 'resolved' WHERE case_id = ? AND status = 'open'",
                (case_id,),
            )
        return result

    def append_review_supplement(
        self, case_id: str, *, idempotency_key: str, evidence: dict
    ) -> dict:
        self.review_case(case_id)
        row = self._db.execute(
            "SELECT evidence_json FROM review_supplements WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row:
            return json.loads(row[0])
        result = {"case_id": case_id, "status": "open", "evidence": evidence}
        supplement_id = f"supplement-{stable_hash([case_id, idempotency_key, evidence])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT INTO review_supplements VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (supplement_id, case_id, idempotency_key, json.dumps(result, sort_keys=True)),
            )
        return result

    def open_review_count(self, run_id: str) -> int:
        return int(
            self._db.execute(
                "SELECT COUNT(*) FROM review_cases WHERE run_id = ? AND status = 'open'",
                (run_id,),
            ).fetchone()[0]
        )

    def review_count(self, run_id: str, *, kinds: tuple[str, ...] | None = None) -> int:
        if not kinds:
            return int(
                self._db.execute(
                    "SELECT COUNT(*) FROM review_cases WHERE run_id = ?", (run_id,)
                ).fetchone()[0]
            )
        placeholders = ",".join("?" for _ in kinds)
        return int(
            self._db.execute(
                f"SELECT COUNT(*) FROM review_cases WHERE run_id = ? AND review_kind IN ({placeholders})",
                (run_id, *kinds),
            ).fetchone()[0]
        )

    def request_data(self, run_id: str) -> dict:
        return json.loads(self.run_row(run_id)["request_json"])

    def prior_staged_questions(self, run_id: str) -> tuple[tuple[str, str], ...]:
        results: list[tuple[str, str]] = []
        prior = self.run_row(run_id)["prior_run_id"]
        while prior:
            rows = self._db.execute(
                "SELECT candidate_id, text FROM candidates WHERE run_id = ? AND state = 'staged' ORDER BY ordinal",
                (prior,),
            ).fetchall()
            results.extend((str(row[0]), str(row[1])) for row in rows)
            prior = self.run_row(str(prior))["prior_run_id"]
        return tuple(results)

    def prior_staged_candidates(self, run_id: str) -> tuple[CandidateReport, ...]:
        results: list[CandidateReport] = []
        prior = self.run_row(run_id)["prior_run_id"]
        while prior:
            results.extend(
                item for item in self.candidates(str(prior)) if item.state == CandidateState.STAGED
            )
            prior = self.run_row(str(prior))["prior_run_id"]
        return tuple(results)

    def prior_diversity_advice(self, run_id: str) -> dict | None:
        prior = self.run_row(run_id)["prior_run_id"]
        while prior:
            row = self._db.execute(
                "SELECT payload_json FROM evidence WHERE run_id=? AND evidence_type='gemini_diversity_advice' ORDER BY rowid DESC LIMIT 1",
                (prior,),
            ).fetchone()
            if row:
                payload = json.loads(row[0])
                if payload.get("status") == "succeeded":
                    return payload["advice"]
                # Do not silently reuse a stale mission after its replacement failed.
                return None
            prior = self.run_row(str(prior))["prior_run_id"]
        return None

    def recent_creative_missions(self, run_id: str, limit: int = 8) -> list[dict]:
        result = []
        current = run_id
        while current and len(result) < limit:
            rows = self._db.execute(
                "SELECT payload_json FROM evidence WHERE run_id=? AND evidence_type='creative_mission' ORDER BY rowid",
                (current,),
            ).fetchall()
            result.extend(json.loads(row[0]) for row in rows)
            current = self.run_row(current)["prior_run_id"]
        return result[:limit]

    def campaign_uncertainty_review_count(self, run_id: str) -> int:
        total = self.review_count(
            run_id,
            kinds=("semantic_uncertainty", "quality_uncertainty", "metadata_uncertainty"),
        )
        prior = self.run_row(run_id)["prior_run_id"]
        if prior:
            total += self.campaign_uncertainty_review_count(str(prior))
        return total

    def add_evidence(
        self,
        *,
        run_id: str,
        candidate_id: str | None,
        evidence_type: str,
        configuration_id: str,
        payload: dict,
    ) -> str:
        evidence_id = f"evidence-{stable_hash([run_id, candidate_id, evidence_type, payload, configuration_id])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO evidence VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    evidence_id,
                    run_id,
                    candidate_id,
                    evidence_type,
                    configuration_id,
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return evidence_id

    def candidate_evidence_summary(self, run_id: str, candidate_id: str) -> dict:
        rows = self._db.execute(
            "SELECT evidence_id, evidence_type, payload_json FROM evidence WHERE run_id = ? AND candidate_id = ? ORDER BY created_at, evidence_id",
            (run_id, candidate_id),
        ).fetchall()
        neighbor_ids: set[str] = set()
        for row in rows:
            payload = json.loads(row["payload_json"])
            neighbor_id = payload.get("neighbor_id")
            if isinstance(neighbor_id, str):
                neighbor_ids.add(neighbor_id)
        return {
            "evidence_ids": [str(row["evidence_id"]) for row in rows],
            "neighbor_ids": sorted(neighbor_ids),
        }

    def configuration_data(self, configuration_id: str) -> dict:
        row = self._db.execute(
            "SELECT payload_json FROM configurations WHERE configuration_id = ?",
            (configuration_id,),
        ).fetchone()
        if not row:
            raise KeyError(configuration_id)
        return json.loads(row[0])

    def candidate(self, candidate_id: str) -> CandidateReport:
        row = self._db.execute(
            "SELECT run_id FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if not row:
            raise KeyError(candidate_id)
        return next(
            item for item in self.candidates(str(row["run_id"]))
            if item.candidate_id == candidate_id
        )

    def candidates(self, run_id: str) -> tuple[CandidateReport, ...]:
        rows = self._db.execute(
            "SELECT * FROM candidates WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        candidates = []
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            if isinstance(metadata.get("uncertain_fields"), list):
                metadata["uncertain_fields"] = tuple(metadata["uncertain_fields"])
            candidates.append(CandidateReport(
                candidate_id=str(row["candidate_id"]),
                text=str(row["text"]),
                level=Level(str(row["level"])),
                strategy=str(row["strategy"]),
                state=CandidateState(str(row["state"])),
                reason_codes=tuple(json.loads(row["reason_codes_json"])),
                theme_memberships=(
                    tuple(json.loads(row["themes_json"]))
                    if row["themes_json"] is not None
                    else None
                ),
                metadata=metadata,
            ))
        return tuple(candidates)

    def ledger_summary(self, run_id: str) -> LedgerSummary:
        run = self.run_row(run_id)
        reconciled, active, unknown = self._ledger_totals(run_id)
        authorized = int(run["authorized_microusd"])
        used = reconciled + active + unknown
        return LedgerSummary(
            authorized_usd=_usd(authorized),
            reconciled_usd=_usd(reconciled),
            active_reserved_usd=_usd(active),
            unknown_usd=_usd(unknown),
            remaining_usd=_usd(max(0, authorized - used)),
        )

    def store_report(self, report: RunReport) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET report_json = ?, status = ?, stop_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (
                    json.dumps(canonical_data(report), sort_keys=True),
                    report.status,
                    report.stop_reason,
                    report.run_id,
                ),
            )
