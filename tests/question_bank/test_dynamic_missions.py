from __future__ import annotations

import copy
import tempfile
import unittest

from question_bank import ProviderResult, ProviderUsage, RunRequest
from question_bank.contracts import Level
from question_bank.engine import EnrichmentEngine
from question_bank.missions import missions_from_advice, validate_missions
from question_bank.providers import _json_schema
from tests.question_bank import test_v21

next_missions = test_v21.next_missions


class MissionValidationTests(unittest.TestCase):
    def test_optional_dimensions_and_stable_slot_order(self):
        missions = next_missions()
        self.assertEqual(missions, validate_missions(list(reversed(missions))))
        self.assertEqual('array',_json_schema('observed_diversity')['properties']['next_missions']['type'])

    def test_malformed_plans_fall_back(self):
        cases = [None, [], next_missions()[:3], next_missions()+next_missions()[:1]]
        for field,value in [('agent_slot',0),('agent_slot',True),('level','deep'),('brief',''),
                            ('brief','x'*401),('theme_hints',['Random']),('contrast',{}),('scenario','')]:
            missions=next_missions()
            missions[1][field]=value
            cases.append(missions)
        duplicate=next_missions();duplicate[1]['brief']=duplicate[0]['brief'];cases.append(duplicate)
        for value in cases:
            with self.subTest(value=value):
                self.assertIsNone(missions_from_advice({'next_missions':value}))


class DynamicMissionIntegrationTests(unittest.TestCase):
    engine = test_v21.BankV21Tests.engine

    def advice(self):
        return {'observations':[], 'avoid_patterns':[], 'explore_directions':[], 'next_missions':next_missions()}

    def test_next_batch_receives_one_mission_each_and_still_generates_five(self):
        with tempfile.TemporaryDirectory() as directory:
            engine,provider,prior,config=self.engine(directory,{})
            advice=self.advice()
            engine._store.add_evidence(run_id=prior,candidate_id=None,evidence_type='gemini_diversity_advice',
                configuration_id=config.manifest_id,payload={'status':'succeeded','advice':advice})
            for index,role in enumerate(config.creative_roles):
                provider.append(role.role,ProviderResult({'questions':[f'Question {index} item {i}?' for i in range(5)]},
                    ProviderUsage(10,0,10,0,20),role.model,f'creative-{index}'))
            request=RunRequest.production_batch(idempotency_key='next',snapshot_id=engine.empty_snapshot_id,
                batch_index=1,authorization_usd='1',configuration_id=config.manifest_id)
            report=engine.run(request,prior_run_id=prior)
            self.assertEqual(20,len(report.candidates))
            self.assertEqual(10,sum(c.level==Level.SHALLOW for c in report.candidates))
            for index,call in enumerate(provider.calls[:4]):
                self.assertEqual(advice['next_missions'][index]['brief'],call.payload['strategy_mission'])
                self.assertNotIn('next_missions',call.payload)
                self.assertEqual(5,len(call.payload['output_schema']['questions']))
                self.assertIn('Level guidance',call.payload['mission_rules'])
            self.assertEqual('quality_medium',provider.calls[4].role.role)
            self.assertEqual(4,len(engine._store.recent_creative_missions(report.run_id)))
            self.assertTrue(all(m['source']=='dynamic' for m in engine._store.recent_creative_missions(report.run_id)))

    def test_failed_latest_report_does_not_reuse_stale_missions(self):
        with tempfile.TemporaryDirectory() as directory:
            engine,_,prior,config=self.engine(directory,{})
            engine._store.add_evidence(run_id=prior,candidate_id=None,evidence_type='gemini_diversity_advice',
                configuration_id=config.manifest_id,payload={'status':'succeeded','advice':self.advice()})
            request=RunRequest.production_batch(idempotency_key='failed',snapshot_id=engine.empty_snapshot_id,
                batch_index=1,authorization_usd='1',configuration_id=config.manifest_id)
            failed,_=engine._store.create_run(request,config.manifest_id,prior_run_id=prior)
            engine._store.add_evidence(run_id=failed,candidate_id=None,evidence_type='gemini_diversity_advice',
                configuration_id=config.manifest_id,payload={'status':'unavailable','reason':'malformed_dynamic_missions'})
            request=RunRequest.production_batch(idempotency_key='next',snapshot_id=engine.empty_snapshot_id,
                batch_index=2,authorization_usd='1',configuration_id=config.manifest_id)
            report=engine.run(request,prior_run_id=failed)
            self.assertIsNone(engine._store.prior_diversity_advice(report.run_id))
            self.assertTrue(all(m['source']=='bootstrap_fallback' for m in engine._store.recent_creative_missions(report.run_id)))

    def test_bad_generated_missions_do_not_change_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            advice=copy.deepcopy(self.advice());advice['next_missions'][0]['level']='deep'
            engine,_,run,config=self.engine(directory,{'observed_diversity':[
                ProviderResult(advice,ProviderUsage(10,0,10,0,20),'gemini-3.5-flash-lite','invalid')
            ]})
            engine._record_diversity_advice(run)
            row=engine._store._db.execute("SELECT payload_json FROM evidence WHERE evidence_type='gemini_diversity_advice'").fetchone()
            self.assertIn('malformed_dynamic_missions',row[0])
            self.assertEqual((),engine._store.candidates(run))


if __name__=='__main__':
    unittest.main()
