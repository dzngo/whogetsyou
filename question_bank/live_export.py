"""Local, read-only campaign export; no credentials or provider calls required."""

from __future__ import annotations

import argparse
import csv
import io
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from question_bank.semantic import normalize_question


def refresh_export(
    database: Path, output: Path, prefix: str, configuration_id: str | None,
    *, per_level: int = 400, replacement_prefix: str | None = None,
) -> int:
    """Atomically export new unique proposals, including unfinished/rejected rows."""
    if not prefix or per_level < 1:
        raise ValueError("prefix and a positive per-level limit are required")
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        first = conn.execute(
            "SELECT min(rowid) FROM runs WHERE substr(idempotency_key,1,?)=? "
            "AND (? IS NULL OR configuration_id=?)", (len(prefix), prefix, configuration_id, configuration_id),
        ).fetchone()[0]
        seen = {
            normalize_question(row[0]) for row in conn.execute(
                "SELECT c.text FROM candidates c JOIN runs r ON r.run_id=c.run_id "
                "WHERE r.rowid < ?", (first,),
            )
        }
        selected: dict[str, list[sqlite3.Row]] = {"shallow": [], "deep": []}
        for row in conn.execute(
            "SELECT c.text,c.level,c.state,c.reason_codes_json FROM candidates c "
            "JOIN runs r ON r.run_id=c.run_id "
            "WHERE substr(r.idempotency_key,1,?)=? AND (? IS NULL OR r.configuration_id=?) "
            "ORDER BY r.rowid,c.ordinal",
            (len(prefix), prefix, configuration_id, configuration_id),
        ):
            normalized = normalize_question(row["text"])
            if normalized and normalized not in seen:
                seen.add(normalized)
                selected[row["level"]].append(row)
        if replacement_prefix:
            # Recovery creates audit copies. Overlay their latest completed
            # outcome without adding another CSV row or modifying originals.
            replacements = {}
            for row in conn.execute(
                "SELECT c.text,c.level,c.state,c.reason_codes_json FROM candidates c "
                "JOIN runs r ON r.run_id=c.run_id WHERE substr(r.idempotency_key,1,?)=? "
                "AND c.state != 'proposed' ORDER BY r.rowid,c.ordinal",
                (len(replacement_prefix), replacement_prefix),
            ):
                replacements[normalize_question(row['text'])] = row
            selected = {level: [replacements.get(normalize_question(row['text']), row)
                                for row in rows] for level, rows in selected.items()}
    finally:
        conn.close()
    rows = selected["shallow"][:per_level] + selected["deep"][:per_level]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("number", "level", "question", "pipeline_state", "reason_codes"))
    for number, row in enumerate(rows, 1):
        writer.writerow((number, row["level"], row["text"], row["state"], row["reason_codes_json"]))
    content = buffer.getvalue().encode("utf-8")
    if output.exists() and output.read_bytes() == content:
        return len(rows)
    # Readers always see a complete CSV, never a partially written export.
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".question-export-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return len(rows)


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        raise RuntimeError("cannot inspect generator process; run the exporter with matching permissions")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--configuration-id", required=True)
    parser.add_argument("--per-level", type=int, default=400)
    parser.add_argument("--watch-pid", type=int)
    args = parser.parse_args()
    if args.watch_pid is not None and args.watch_pid <= 0:
        parser.error("--watch-pid must be positive")
    previous_count = None
    while True:
        # Check before exporting to ensure one final refresh after process exit.
        alive = args.watch_pid is not None and process_exists(args.watch_pid)
        count = refresh_export(
            args.database, args.output, args.prefix, args.configuration_id,
            per_level=args.per_level,
        )
        if count != previous_count or not alive:
            print(f"Exported {count} questions to {args.output}", flush=True)
            previous_count = count
        if not alive:
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
