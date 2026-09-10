from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from question_bank import ConfigurationManifest, EnrichmentEngine, HashingTestEmbedder, ProviderFailure, ProviderResult, ProviderUsage, RunRequest, ScriptedProvider
from question_bank.contracts import CandidateReport, CandidateState, Level
from question_bank.providers import _provider_failure
from question_bank.question_style import SHALLOW_GUIDANCE


def next_missions():
    return [dict(agent_slot=slot, level='shallow' if slot < 2 else 'deep',
                 brief=f'Explore different everyday subjects in direction {slot}.',
                 aspect=None, scenario=None, perspective=None, contrast=None, theme_hints=[])
            for slot in range(4)]


class BankV21Tests(unittest.TestCase):
    def engine(self, directory, responses):
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        provider = ScriptedProvider(responses)
        engine = EnrichmentEngine(Path(directory), provider=provider, configuration=config, embedder=HashingTestEmbedder())
        request = RunRequest.production_batch(idempotency_key='test', snapshot_id=engine.empty_snapshot_id,
            batch_index=0, authorization_usd='1', configuration_id=config.manifest_id)
        run_id, _ = engine._store.create_run(request, config.manifest_id)
        self.addCleanup(engine.close)
        return engine, provider, run_id, config

    def test_shallow_missions_rotate_and_quality_uses_same_standard(self):
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        missions = set()
        for batch in range(5):
            for role in config.creative_roles[:2]:
                payload = EnrichmentEngine._creative_payload(role, Level.SHALLOW, batch_index=batch)
                self.assertEqual(SHALLOW_GUIDANCE, payload['level_guidance'])
                missions.add(payload['strategy_mission'])
        self.assertEqual(10, len(missions))
        self.assertEqual(SHALLOW_GUIDANCE, EnrichmentEngine._quality_payload(())['level_definitions']['shallow'])

    @patch('question_bank.engine.time.sleep')
    def test_503_rotates_and_accounts_for_each_attempt(self, sleep):
        with tempfile.TemporaryDirectory() as directory:
            name = 'creative_concrete_life_moments'
            engine, provider, run_id, config = self.engine(directory, {name: [
                ProviderFailure('provider_unavailable_503', ambiguous=True),
                ProviderFailure('provider_unavailable_503', ambiguous=True),
                ProviderFailure('provider_unavailable_503', ambiguous=True),
                ProviderResult({'questions': []}, ProviderUsage(10,0,10,0,20), 'gemini-3.5-flash-lite', 'ok'),
            ]})
            engine._invoke(run_id, config.role(name), {})
            self.assertEqual(['gemini-3.5-flash-lite','gemini-3-flash-preview','gemini-3.6-flash','gemini-3.5-flash-lite'],
                             [call.role.model for call in provider.calls])
            rows = engine._store._db.execute('SELECT state FROM ledger_entries WHERE run_id=?',(run_id,)).fetchall()
            self.assertEqual(3, sum(row[0]=='unknown' for row in rows))
            self.assertEqual(1, sum(row[0]=='reconciled' for row in rows))
            self.assertEqual([1,2,4], [call.args[0] for call in sleep.call_args_list])

    def test_non_503_does_not_switch_models(self):
        with tempfile.TemporaryDirectory() as directory:
            name = 'creative_concrete_life_moments'
            engine, provider, run_id, config = self.engine(directory, {name: [ProviderFailure('provider_rate_limited', ambiguous=False)]})
            with self.assertRaises(ProviderFailure):
                engine._invoke(run_id, config.role(name), {})
            self.assertEqual(1,len(provider.calls))
        self.assertEqual('provider_unavailable_503', _provider_failure(SimpleNamespace(code=503)).reason)

    @patch('question_bank.engine.time.sleep')
    def test_fallback_stops_when_reservation_would_exceed_budget(self, sleep):
        with tempfile.TemporaryDirectory() as directory:
            name = 'creative_concrete_life_moments'
            engine, provider, run_id, config = self.engine(directory, {name:[
                ProviderFailure('provider_unavailable_503',ambiguous=True),
            ]})
            engine._store._db.execute('UPDATE runs SET authorized_microusd=15000 WHERE run_id=?',(run_id,))
            engine._store._db.commit()
            with self.assertRaises(ProviderFailure) as caught:
                engine._invoke(run_id,config.role(name),{})
            self.assertEqual('budget_or_attempt_exhausted',caught.exception.reason)
            self.assertEqual(1,len(provider.calls))

    @patch('question_bank.engine.time.sleep')
    def test_four_503s_stop_without_an_infinite_cycle(self, sleep):
        with tempfile.TemporaryDirectory() as directory:
            name = 'creative_concrete_life_moments'
            engine, provider, run_id, config = self.engine(directory,{name:[
                ProviderFailure('provider_unavailable_503',ambiguous=True) for _ in range(4)
            ]})
            with self.assertRaises(ProviderFailure):
                engine._invoke(run_id,config.role(name),{})
            self.assertEqual(4,len(provider.calls))

    def test_gemini_advice_is_saved_and_does_not_change_admission(self):
        advice = {'observations':['Mostly food.'], 'avoid_patterns':['Shallow: repeated snack choices.'],
                  'explore_directions':['Shallow: everyday skills.'], 'next_missions':next_missions()}
        with tempfile.TemporaryDirectory() as directory:
            engine, provider, run_id, config = self.engine(directory, {'observed_diversity':[
                ProviderResult(advice,ProviderUsage(10,0,10,0,20),'gemini-3.5-flash-lite','advice')
            ]})
            candidate = CandidateReport('c1',"What's my favorite food?",Level.SHALLOW,'test',CandidateState.STAGED)
            engine._store.add_candidates(run_id,(candidate,))
            engine._record_diversity_advice(run_id)
            self.assertEqual('gemini',provider.calls[0].role.provider)
            self.assertEqual(CandidateState.STAGED,engine._store.candidates(run_id)[0].state)
            request = RunRequest.production_batch(idempotency_key='next',snapshot_id=engine.empty_snapshot_id,
                batch_index=1,authorization_usd='1',configuration_id=config.manifest_id)
            next_id,_=engine._store.create_run(request,config.manifest_id,prior_run_id=run_id)
            self.assertEqual(advice,engine._store.prior_diversity_advice(next_id))

    def test_diversity_failure_keeps_staged_question(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, _, run_id, _ = self.engine(directory, {})
            engine._store.add_candidates(run_id,(CandidateReport('c1','Favorite color?',Level.SHALLOW,'test',CandidateState.STAGED),))
            engine._record_diversity_advice(run_id)
            self.assertEqual(CandidateState.STAGED,engine._store.candidates(run_id)[0].state)


if __name__ == '__main__':
    unittest.main()
