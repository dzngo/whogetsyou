from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from question_bank import (
    ConfigurationManifest,
    EnrichmentEngine,
    HashingTestEmbedder,
    ProviderFailure,
    ProviderResult,
    ProviderUsage,
    RunRequest,
    ScriptedProvider,
)
from question_bank.contracts import Level, canonical_data, stable_hash
from question_bank.store import V2Store


class BudgetAndCacheTests(unittest.TestCase):
    def test_large_campaign_scales_attempt_and_uncertainty_limits_explicitly(self) -> None:
        request = RunRequest.production_batch(
            idempotency_key="large-campaign",
            snapshot_id="snapshot",
            batch_index=0,
            authorization_usd=Decimal("6.80"),
            attempt_limit=500,
            uncertainty_review_limit=30,
        )

        self.assertEqual(500, request.attempt_limit)
        self.assertEqual(30, request.uncertainty_review_limit)

    def test_production_campaign_shares_attempt_and_exposure_limits_across_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ConfigurationManifest.approved_defaults(
                named_themes=(), aspects=(), perspectives=()
            )
            store = V2Store(root)
            snapshot = store.ensure_empty_snapshot()
            first_request = replace(
                RunRequest.production_batch(
                    idempotency_key="campaign-one", snapshot_id=snapshot, batch_index=0
                ),
                authorization_usd=Decimal("0.10"),
                attempt_limit=2,
            )
            first_run, _ = store.create_run(first_request, config.manifest_id)
            self.assertIsNotNone(
                store.reserve(
                    first_run,
                    invocation_key="first",
                    role="test",
                    provider="test",
                    model="test",
                    reservation_usd=Decimal("0.04"),
                    input_hash="first",
                )
            )
            second_request = replace(
                RunRequest.production_batch(
                    idempotency_key="campaign-two", snapshot_id=snapshot, batch_index=1
                ),
                authorization_usd=Decimal("0.10"),
                attempt_limit=2,
            )
            second_run, _ = store.create_run(
                second_request, config.manifest_id, prior_run_id=first_run
            )

            self.assertIsNotNone(
                store.reserve(
                    second_run,
                    invocation_key="second",
                    role="test",
                    provider="test",
                    model="test",
                    reservation_usd=Decimal("0.04"),
                    input_hash="second",
                )
            )
            self.assertIsNone(
                store.reserve(
                    second_run,
                    invocation_key="third",
                    role="test",
                    provider="test",
                    model="test",
                    reservation_usd=Decimal("0.01"),
                    input_hash="third",
                )
            )
            self.assertEqual(2, store.campaign_attempt_count(second_run))
            self.assertEqual(Decimal("0.080000"), store.ledger_summary(second_run).active_reserved_usd)
            store.close()

    def test_interrupted_active_reservation_becomes_unknown_before_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ConfigurationManifest.approved_defaults(
                named_themes=(), aspects=(), perspectives=()
            )
            store = V2Store(root)
            store.install_configuration(config)
            request = RunRequest.pilot(
                idempotency_key="interrupted", snapshot_id=store.ensure_empty_snapshot()
            )
            run_id, _ = store.create_run(request, config.manifest_id)
            role = config.creative_roles[0]
            payload = EnrichmentEngine._creative_payload(
                role, Level.SHALLOW, batch_index=0, avoid_patterns=()
            )
            input_hash = stable_hash(
                {
                    "configuration": config.manifest_id,
                    "role": canonical_data(role),
                    "payload": payload,
                }
            )
            self.assertIsNotNone(
                store.reserve(
                    run_id,
                    invocation_key="interrupted-call",
                    role=role.role,
                    provider=role.provider,
                    model=role.model,
                    reservation_usd=role.reservation_usd,
                    input_hash=input_hash,
                )
            )
            store.close()
            provider = ScriptedProvider()
            engine = EnrichmentEngine(
                root,
                provider=provider,
                configuration=config,
                embedder=HashingTestEmbedder(),
            )

            report = engine.resume(
                run_id,
                RunRequest.pilot(
                    idempotency_key="interrupted-resume",
                    snapshot_id=engine.empty_snapshot_id,
                    authorization_usd=Decimal("0.23"),
                ),
            )

            self.assertEqual(role.reservation_usd, report.ledger.unknown_usd)
            self.assertEqual((), provider.calls)
            engine.close()

    def test_concurrent_reservations_cannot_exceed_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
            store = V2Store(root)
            store.install_configuration(config)
            request = replace(
                RunRequest.pilot(idempotency_key="atomic", snapshot_id=store.ensure_empty_snapshot()),
                authorization_usd=Decimal("0.050000"), attempt_limit=20,
            )
            run_id, _ = store.create_run(request, config.manifest_id)
            store.close()
            results = []
            lock = threading.Lock()

            def reserve(index):
                worker = V2Store(root)
                value = worker.reserve(
                    run_id, invocation_key=f"call-{index}", role="test", provider="test",
                    model="test", reservation_usd=Decimal("0.010000"), input_hash=f"hash-{index}",
                )
                with lock:
                    results.append(value)
                worker.close()

            threads = [threading.Thread(target=reserve, args=(index,)) for index in range(10)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            check = V2Store(root)
            self.assertEqual(5, sum(result is not None for result in results))
            self.assertEqual(Decimal("0.050000"), check.ledger_summary(run_id).active_reserved_usd)
            check.close()

    def test_ambiguous_failure_keeps_full_unknown_reservation_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
            provider = ScriptedProvider({config.creative_roles[0].role: [ProviderFailure("timeout", ambiguous=True)]})
            engine = EnrichmentEngine(Path(directory), provider=provider, configuration=config, embedder=HashingTestEmbedder())
            report = engine.run(RunRequest.pilot(idempotency_key="unknown", snapshot_id=engine.empty_snapshot_id))
            self.assertEqual("unknown_spend", report.stop_reason)
            self.assertEqual(config.creative_roles[0].reservation_usd, report.ledger.unknown_usd)
            self.assertEqual(1, len(provider.calls))
            engine.close()

    def test_exact_creative_cache_reuse_costs_zero_attempts(self) -> None:
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        responses = {}
        for role_index, role in enumerate(config.creative_roles):
            responses[role.role] = [ProviderResult(
                {"questions": [f"What unique cached detail {role_index}-{index} matters?" for index in range(5)]},
                ProviderUsage(500, 0, 50, 50, 600), role.model, f"creative-{role_index}",
            )]
        responses["quality_medium"] = [ProviderFailure("stop-one", ambiguous=False), ProviderFailure("stop-two", ambiguous=False)]
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            engine = EnrichmentEngine(Path(directory), provider=provider, configuration=config, embedder=HashingTestEmbedder())
            first = engine.run(RunRequest.pilot(idempotency_key="cache-one", snapshot_id=engine.empty_snapshot_id))
            second = engine.run(RunRequest.pilot(idempotency_key="cache-two", snapshot_id=engine.empty_snapshot_id))
            self.assertEqual(0, first.cache_hits)
            self.assertEqual(4, second.cache_hits)
            self.assertEqual(1, second.attempts)
            self.assertEqual(6, len(provider.calls))
            engine.close()

    def test_stale_price_catalog_fails_before_provider_invocation(self) -> None:
        config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
        stale = replace(config, prices=tuple(replace(price, valid_through="2020-01-01") for price in config.prices))
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            with self.assertRaisesRegex(ValueError, "price"):
                EnrichmentEngine(Path(directory), provider=provider, configuration=stale, embedder=HashingTestEmbedder())
            self.assertEqual((), provider.calls)

    def test_resume_retains_unknown_spend_and_never_repeats_ambiguous_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = ConfigurationManifest.approved_defaults(named_themes=(), aspects=(), perspectives=())
            provider = ScriptedProvider({config.creative_roles[0].role: [ProviderFailure("timeout", ambiguous=True)]})
            engine = EnrichmentEngine(Path(directory), provider=provider, configuration=config, embedder=HashingTestEmbedder())
            first = engine.run(RunRequest.pilot(idempotency_key="unknown-first", snapshot_id=engine.empty_snapshot_id))
            resumed = engine.resume(
                first.run_id,
                RunRequest.pilot(
                    idempotency_key="unknown-resume", snapshot_id=engine.empty_snapshot_id,
                    authorization_usd=Decimal("0.23"),
                ),
            )
            self.assertNotEqual(first.run_id, resumed.run_id)
            self.assertEqual(first.ledger.unknown_usd, resumed.ledger.unknown_usd)
            self.assertEqual(1, len(provider.calls))
            self.assertEqual(0, resumed.attempts)
            engine.close()


if __name__ == "__main__":
    unittest.main()
