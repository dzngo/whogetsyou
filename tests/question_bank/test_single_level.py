import tempfile
import unittest

from question_bank import ProviderResult, ProviderUsage, RunRequest
from question_bank.contracts import CandidateReport, CandidateState, Level
from question_bank.missions import validate_missions
from tests.question_bank import test_v21


class SingleLevelTests(unittest.TestCase):
    engine = test_v21.BankV21Tests.engine

    def test_shallow_only_generates_twenty_and_writes_four_shallow_missions(self):
        with tempfile.TemporaryDirectory() as directory:
            engine,provider,_,config=self.engine(directory,{})
            for index,role in enumerate(config.creative_roles):
                provider.append(role.role,ProviderResult({'questions':[f'Everyday item {index} choice {i}?' for i in range(5)]},
                    ProviderUsage(10,0,10,0,20),role.model,str(index)))
            request=RunRequest.production_batch(idempotency_key='shallow',snapshot_id=engine.empty_snapshot_id,
                batch_index=0,authorization_usd='1',configuration_id=config.manifest_id,levels=(Level.SHALLOW,))
            report=engine.run(request)
            self.assertEqual(20,len(report.candidates))
            self.assertTrue(all(c.level==Level.SHALLOW for c in report.candidates))
            self.assertEqual(4,len({c.payload['strategy_mission'] for c in provider.calls[:4]}))
            missions=test_v21.next_missions()
            for m in missions:m['level']='shallow'
            self.assertEqual(missions,validate_missions(missions,('shallow',)))
            provider.append('observed_diversity',ProviderResult(dict(observations=[],avoid_patterns=[],explore_directions=[],next_missions=missions),
                ProviderUsage(10,0,10,0,20),'gemini-3.5-flash-lite','advice'))
            engine._record_diversity_advice(report.run_id)
            self.assertTrue(all(s['level']=='shallow' for s in provider.calls[-1].payload['next_agent_slots']))

    def test_existing_bank_question_is_a_repeat_without_linking_old_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            engine,_,old,config=self.engine(directory,{})
            question=CandidateReport('old-question',"What's my favorite color?",Level.SHALLOW,'old',CandidateState.STAGED)
            engine._store.add_candidates(old,(question,))
            request=RunRequest.production_batch(idempotency_key='new',snapshot_id=engine.empty_snapshot_id,
                batch_index=0,authorization_usd='1',configuration_id=config.manifest_id,
                levels=(Level.SHALLOW,),comparison_candidate_ids=('old-question',))
            run,_=engine._store.create_run(request,config.manifest_id)
            duplicate=CandidateReport('new-question',question.text,Level.SHALLOW,'new',CandidateState.PROPOSED)
            engine._store.add_candidates(run,(duplicate,))
            outcomes,_=engine._local_semantic_scan(run,(duplicate,))
            self.assertEqual('reject',outcomes['new-question'])
            self.assertIsNone(engine._store.run_row(run)['prior_run_id'])
