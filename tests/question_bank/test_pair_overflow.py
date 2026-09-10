from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from question_bank import (
    CandidateState, ConfigurationManifest, EnrichmentEngine, HashingTestEmbedder,
    ProviderFailure, ProviderResult, ProviderUsage, RunRequest, ScriptedProvider,
)


class PairOverflowTests(unittest.TestCase):
    def exercise(self, failure=None):
        questions = runpy.run_path(str(Path(__file__).with_name('test_engine_v2.py')))['DIVERSE_QUESTIONS']
        config = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=(), local_distance_authority=True)
        usage = ProviderUsage(1000, 0, 100, 100, 1200)
        responses = {role.role: [ProviderResult(
            {'questions': list(questions[i*5:i*5+5])}, usage, role.model, str(i))]
            for i, role in enumerate(config.creative_roles)}

        def quality(call):
            return ProviderResult({'records': [dict(
                candidate_id=c['candidate_id'], clarity='pass', answerability='pass',
                emotional_safety='pass', level_fit='pass',
                deep_revelation='not_applicable' if c['level']=='shallow' else 'pass',
                reason_codes=['passes']) for c in call.payload['candidates']]},
                usage, call.role.model, call.invocation_id)

        def distinct(call):
            return ProviderResult({'pairs': [dict(
                pair_id=p['pair_id'], scenario='different', perspective='different',
                answer_space='different', aspect='different', wording='different',
                verdict='distinct', reason_codes=['different_meaning'])
                for p in call.payload['pairs']]}, usage, call.role.model, call.invocation_id)

        def scan(run, candidates):
            outcomes = {c.candidate_id: 'pass' for c in candidates}
            pairs = []
            for i in range(30):
                c = candidates[0 if i < 6 else 1]
                outcomes[c.candidate_id] = 'pending'
                pairs.append(dict(candidate_id=c.candidate_id, candidate_text=c.text,
                    neighbor_id=f'neighbor-{i}', neighbor_text=f'Other question {i}?',
                    embedding_cosine=.8, token_containment=.5, character_cosine=.7,
                    token_jaccard=.4, pair_id=str(i)))
            return outcomes, pairs

        responses['quality_medium'] = [quality, quality]
        responses['semantic_high'] = [distinct] + ([failure] if failure else [distinct]*4)
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(Path(directory), configuration=config,
                provider=provider, embedder=HashingTestEmbedder())
            try:
                with patch.object(engine, '_local_semantic_scan', side_effect=scan):
                    report = engine.run(RunRequest.production_batch(
                        idempotency_key='overflow', snapshot_id=engine.empty_snapshot_id,
                        batch_index=0, authorization_usd='6.00'))
                calls = [c for c in provider.calls if c.role.role == 'semantic_high']
                return report, calls
            finally:
                engine.close()

    def test_more_than_24_pairs_are_processed_in_six_pair_calls(self):
        report, calls = self.exercise()
        self.assertEqual([6]*5, [len(c.payload['pairs']) for c in calls])
        self.assertEqual(20, sum(c.state == CandidateState.STAGED for c in report.candidates))
        self.assertFalse(any('pair_overflow' in c.reason_codes for c in report.candidates))

    def test_failure_preserves_completed_and_local_passes(self):
        for reason in ('provider_output_incomplete_max_output_tokens', 'budget_exhausted'):
            with self.subTest(reason=reason):
                report, calls = self.exercise(ProviderFailure(reason, ambiguous=False))
                self.assertEqual(2, len(calls))
                self.assertEqual(19, sum(c.state == CandidateState.STAGED for c in report.candidates))
                unresolved = [c for c in report.candidates if c.state == CandidateState.OPERATIONALLY_UNRESOLVED]
                self.assertEqual(1, len(unresolved))
                self.assertIn(reason, unresolved[0].reason_codes)
