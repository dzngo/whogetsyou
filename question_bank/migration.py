"""Read-only legacy inventory and one-way archive creation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from question_bank.contracts import stable_hash


@dataclass(frozen=True)
class MigrationManifest:
    manifest_id: str
    source_hashes: dict[str, str]
    inventory: dict[str, int]
    imported_records: int
    archive_directory: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count(path: Path, table: str, where: str = "") -> int:
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0])
    finally:
        connection.close()


def archive_legacy_storage(
    source_directory: Path,
    archive_directory: Path,
    *,
    expected_inventory: dict[str, int] | None = None,
    acknowledge_difference: bool = False,
) -> MigrationManifest:
    bank = source_directory / "question_bank.sqlite3"
    workflow = source_directory / "workflow.sqlite3"
    if not bank.is_file() or not workflow.is_file():
        raise FileNotFoundError("both legacy SQLite files are required")
    inventory = {
        "accepted_questions": _count(bank, "questions"),
        "open_review_cases": _count(workflow, "review_cases", "WHERE status = 'open'"),
        "agent_invocations": _count(workflow, "agent_invocations"),
        "taxonomy_versions": _count(workflow, "taxonomy_versions"),
    }
    if expected_inventory is not None and inventory != expected_inventory and not acknowledge_difference:
        raise ValueError("legacy inventory differs; explicit operator acknowledgment is required")
    source_hashes = {bank.name: _sha256(bank), workflow.name: _sha256(workflow)}
    payload = {"source_hashes": source_hashes, "inventory": inventory, "imported_records": 0}
    manifest_id = f"migration-{stable_hash(payload)[:24]}"
    archive_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_directory / "migration-manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("manifest_id") != manifest_id:
            raise ValueError("archive directory contains a different migration manifest")
    else:
        for source in (bank, workflow):
            destination = archive_directory / source.name
            shutil.copy2(source, destination)
            os.chmod(destination, 0o444)
        manifest = MigrationManifest(
            manifest_id, source_hashes, inventory, 0, str(archive_directory.resolve())
        )
        manifest_path.write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(manifest_path, 0o444)
    return MigrationManifest(
        manifest_id, source_hashes, inventory, 0, str(archive_directory.resolve())
    )
