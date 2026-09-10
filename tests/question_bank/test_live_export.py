from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from question_bank.live_export import refresh_export


class LiveExportTests(unittest.TestCase):
    def test_exports_partial_campaign_and_refreshes_states(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "bank.sqlite3"
            output = Path(directory) / "questions.csv"
            with sqlite3.connect(database) as conn:
                conn.executescript("""
                    CREATE TABLE runs (run_id TEXT, idempotency_key TEXT,
                        configuration_id TEXT, request_json TEXT);
                    CREATE TABLE candidates (run_id TEXT, ordinal INTEGER,
                        text TEXT, level TEXT, state TEXT, reason_codes_json TEXT);
                    INSERT INTO runs VALUES ('old','old','cfg','{}');
                    INSERT INTO runs VALUES ('new','campaign-0','cfg','{"batch_index":0}');
                    INSERT INTO candidates VALUES ('old',0,'Existing?','deep','staged','[]');
                    INSERT INTO candidates VALUES ('new',0,'Existing!','deep','rejected','[]');
                    INSERT INTO candidates VALUES ('new',1,'New, question?','shallow','proposed','[]');
                    INSERT INTO candidates VALUES ('new',2,'New question!','shallow','rejected','[]');
                    INSERT INTO candidates VALUES ('new',3,'Another?','deep','rejected','["quality"]');
                """)
            self.assertEqual(2, refresh_export(database, output, "campaign-", "cfg"))
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(["New, question?", "Another?"], [r["question"] for r in rows])
            self.assertEqual("proposed", rows[0]["pipeline_state"])
            timestamp = output.stat().st_mtime_ns
            refresh_export(database, output, "campaign-", "cfg")
            self.assertEqual(timestamp, output.stat().st_mtime_ns)
            with sqlite3.connect(database) as conn:
                conn.execute("UPDATE candidates SET state='staged' WHERE run_id='new' AND ordinal=1")
            refresh_export(database, output, "campaign-", "cfg")
            with output.open(newline="") as handle:
                self.assertEqual("staged", next(csv.DictReader(handle))["pipeline_state"])
            self.assertEqual(2, refresh_export(database, output, "campaign-", "cfg", per_level=1))
            with sqlite3.connect(database) as conn:
                conn.execute("INSERT INTO runs VALUES ('repair','campaign-repair-0','cfg2','{}')")
                conn.execute("INSERT INTO candidates VALUES ('repair',0,'New, question?','shallow','rejected','[\"semantic_repeat\"]')")
            self.assertEqual(2, refresh_export(database, output, "campaign-", None,
                                               replacement_prefix="campaign-repair-"))
            with output.open(newline="") as handle:
                repaired = list(csv.DictReader(handle))
            self.assertEqual('rejected', repaired[0]['pipeline_state'])
            self.assertEqual('["semantic_repeat"]', repaired[0]['reason_codes'])


if __name__ == "__main__":
    unittest.main()
