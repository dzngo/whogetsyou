from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from question_bank.migration import archive_legacy_storage
from question_bank.store import V2Store


class MigrationTests(unittest.TestCase):
    def test_version_two_store_refuses_a_legacy_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = sqlite3.connect(root / "question_bank_v2.sqlite3")
            database.execute("CREATE TABLE legacy_questions(id TEXT)")
            database.commit()
            database.close()

            with self.assertRaisesRegex(ValueError, "legacy"):
                V2Store(root)

    def test_legacy_archive_is_hashed_read_only_and_imports_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy"
            source.mkdir()
            bank = sqlite3.connect(source / "question_bank.sqlite3")
            bank.execute("CREATE TABLE questions(id TEXT)")
            bank.commit(); bank.close()
            workflow = sqlite3.connect(source / "workflow.sqlite3")
            workflow.executescript(
                "CREATE TABLE review_cases(status TEXT); CREATE TABLE agent_invocations(id TEXT); CREATE TABLE taxonomy_versions(id TEXT);"
            )
            workflow.execute("INSERT INTO review_cases VALUES ('open')")
            workflow.commit(); workflow.close()
            archive = root / "archive"
            expected = {"accepted_questions": 0, "open_review_cases": 1, "agent_invocations": 0, "taxonomy_versions": 0}

            manifest = archive_legacy_storage(source, archive, expected_inventory=expected)
            repeated = archive_legacy_storage(source, archive, expected_inventory=expected)

            self.assertEqual(manifest, repeated)
            self.assertEqual(0, manifest.imported_records)
            self.assertEqual(0o444, (archive / "question_bank.sqlite3").stat().st_mode & 0o777)
            with self.assertRaisesRegex(ValueError, "acknowledgment"):
                archive_legacy_storage(source, root / "other", expected_inventory={**expected, "agent_invocations": 2})


if __name__ == "__main__":
    unittest.main()
