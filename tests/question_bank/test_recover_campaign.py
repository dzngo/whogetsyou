import json
import sqlite3
import unittest
from decimal import Decimal

from question_bank.recover_campaign import build_plan


class RecoveryPlanTests(unittest.TestCase):
    def test_deducts_spent_and_uncertain_exposure_and_deduplicates_sources(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('''
                CREATE TABLE runs (run_id TEXT,idempotency_key TEXT,authorized_microusd INTEGER,request_json TEXT);
                CREATE TABLE candidates (candidate_id TEXT,run_id TEXT,ordinal INTEGER,text TEXT,state TEXT,reason_codes_json TEXT);
                CREATE TABLE ledger_entries (run_id TEXT,state TEXT,reserved_microusd INTEGER,actual_microusd INTEGER);
                INSERT INTO runs VALUES ('r','campaign-batch-0',6000000,'{"batch_index":0}');
                INSERT INTO ledger_entries VALUES ('r','reconciled',900000,700000);
                INSERT INTO ledger_entries VALUES ('r','active',200000,0);
                INSERT INTO ledger_entries VALUES ('r','unknown',100000,0);
                INSERT INTO candidates VALUES ('a','r',0,'A question?','operationally_unresolved','["pair_overflow"]');
                INSERT INTO candidates VALUES ('b','r',1,'A question!','operationally_unresolved','["pair_overflow"]');
                INSERT INTO candidates VALUES ('c','r',2,'Trusted?','staged','[]');
                INSERT INTO candidates VALUES ('d','r',3,'Trusted!','operationally_unresolved','["pair_overflow"]');
            ''')
            plan = build_plan(db, 'campaign', Decimal('6'), 800)
            self.assertEqual(Decimal('5'), Decimal(plan['authorization_usd']))
            self.assertEqual(['a'], plan['source_candidate_ids'])
            self.assertEqual(['c'], plan['comparison_candidate_ids'])
            self.assertEqual(4, plan['original_saved_proposals'])
            self.assertLessEqual(plan['original_saved_proposals']+20*plan['generation_batches'],800)
            with self.assertRaises(ValueError):
                build_plan(db, 'campaign', Decimal('7'), 800)
