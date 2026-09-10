from __future__ import annotations

from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path

from question_bank import (
    ConfigurationManifest,
    EnrichmentEngine,
    HashingTestEmbedder,
    ProviderResult,
    ProviderUsage,
    RunRequest,
    ScriptedProvider,
)
from question_bank.observability import SafeObservability, _safe_error
from question_bank.observability import PhoenixObservability
from question_bank.contracts import ReservedInvocation


class _RecordingObservation:
    def __init__(self, events):
        self.events = events

    def success(self, result=None, *, actual_cost=None):
        self.events.append(("success", result, actual_cost))

    def failure(self, failure):
        self.events.append(("failure", failure))


class _RecordingObservability:
    def __init__(self):
        self.events = []

    @contextmanager
    def batch(self, request):
        self.events.append(("batch", request))
        yield _RecordingObservation(self.events)

    @contextmanager
    def invocation(self, invocation, rendered_request, *, fallback_attempt=0):
        self.events.append(
            ("invocation", invocation, rendered_request, fallback_attempt)
        )
        yield _RecordingObservation(self.events)

    def close(self):
        self.events.append(("close",))


class _BrokenObservability:
    @contextmanager
    def batch(self, request):
        raise RuntimeError("dashboard unavailable")
        yield

    def close(self):
        raise RuntimeError("dashboard unavailable")


class ObservabilityTests(unittest.TestCase):
    def test_campaign_batch_stage_and_provider_form_one_closed_trace(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        observer = PhoenixObservability.__new__(PhoenixObservability)
        observer._provider = provider
        observer._tracer = provider.get_tracer("question-bank-test")
        observer._campaign_spans = {}
        observer._batch_spans = {}
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        role = configuration.creative_roles[0]
        invocation = ReservedInvocation(
            run_id="run-one", invocation_id="invocation-one",
            idempotency_key="key", role=role, payload={"level": "shallow"},
            reservation_id="reservation-one",
        )
        result = ProviderResult(
            {"questions": ["What is my favorite snack?"]},
            ProviderUsage(10, 0, 10, 0, 20),
            role.model, "response-one",
        )

        with observer.stage(
            "campaign-one", "creative_agent_1", {"batch_index": 0}
        ) as stage:
            with observer.invocation(invocation, {"model": role.model}) as call:
                call.success(result, actual_cost="0.001")
            stage.success({"proposals": 1})
        observer.finish_batch("campaign-one", 0, "completed")
        observer.finish_campaign("campaign-one", "completed")
        spans = {span.name: span for span in exporter.get_finished_spans()}

        campaign = spans["Campaign campaign-one"]
        batch = spans["Batch 0"]
        workflow_stage = spans["creative_agent_1"]
        provider_call = spans[role.role]
        self.assertIsNone(campaign.parent)
        self.assertEqual(campaign.context.span_id, batch.parent.span_id)
        self.assertEqual(batch.context.span_id, workflow_stage.parent.span_id)
        self.assertEqual(workflow_stage.context.span_id, provider_call.parent.span_id)
        self.assertEqual({}, observer._campaign_spans)
        self.assertEqual({}, observer._batch_spans)

    def test_real_invocation_records_rendered_request_response_and_cost(self):
        configuration = ConfigurationManifest.approved_defaults(
            named_themes=(), aspects=(), perspectives=()
        )
        role = configuration.creative_roles[0]
        result = ProviderResult(
            {"questions": ["What is my favorite snack?"] * 5},
            ProviderUsage(10, 0, 10, 0, 20),
            role.model,
            "response-one",
        )
        observer = _RecordingObservability()
        with tempfile.TemporaryDirectory() as directory:
            engine = EnrichmentEngine(
                Path(directory),
                provider=ScriptedProvider({role.role: [result]}),
                configuration=configuration,
                embedder=HashingTestEmbedder(),
                observability=observer,
            )
            request = RunRequest.production_batch(
                idempotency_key="trace-test",
                snapshot_id=engine.empty_snapshot_id,
                batch_index=0,
                authorization_usd="1",
                configuration_id=configuration.manifest_id,
            )
            run_id, _ = engine._store.create_run(request, configuration.manifest_id)

            engine._invoke(run_id, role, {"level": "shallow"})
            engine.close()

        invocation = next(event for event in observer.events if event[0] == "invocation")
        self.assertEqual(0, invocation[3])
        self.assertEqual(role.model, invocation[2]["model"])
        self.assertIn("thinking_config", invocation[2]["config"])
        success = next(event for event in observer.events if event[0] == "success")
        self.assertIs(result, success[1])
        self.assertIsNotNone(success[2])

    def test_observability_failure_does_not_change_batch_result(self):
        observer = SafeObservability(_BrokenObservability())
        request = object()
        with observer.batch(request) as observation:
            observation.success()
        observer.close()

    def test_error_sanitizer_redacts_common_credentials(self):
        sanitized = _safe_error(
            "Authorization: Bearer secret-token API_KEY=private-value sk-abcdefghijk"
        )
        self.assertNotIn("secret-token", sanitized)
        self.assertNotIn("private-value", sanitized)
        self.assertNotIn("abcdefghijk", sanitized)


if __name__ == "__main__":
    unittest.main()
