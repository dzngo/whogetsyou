"""Optional Phoenix tracing for real Question Bank provider invocations."""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
import re
import sys

from question_bank.contracts import ProviderResult, ReservedInvocation, RunReport, RunRequest, canonical_data


LOGGER = logging.getLogger(__name__)
_SECRET = re.compile(r"(?i)(authorization[\"': =]+bearer\s+|api[_-]?key[\"': =]+|sk-[a-z0-9_-]{8})[^\s\"']+")


def _json(value) -> str:
    return json.dumps(canonical_data(value), ensure_ascii=False, sort_keys=True)


def _safe_error(value: str) -> str:
    return _SECRET.sub(r"\1<REDACTED>", value)[:4000]


class _NoopObservation:
    def success(self, result=None, *, actual_cost=None):
        pass

    def failure(self, failure):
        pass


class NoopObservability:
    @contextmanager
    def batch(self, request):
        yield _NoopObservation()

    @contextmanager
    def invocation(self, invocation, rendered_request, *, fallback_attempt=0):
        yield _NoopObservation()

    @contextmanager
    def stage(self, campaign_id, stage, node_input):
        yield _NoopObservation()

    def close(self):
        pass

    def finish_campaign(self, campaign_id, status):
        pass

    def finish_batch(self, campaign_id, batch_index, status):
        pass


class _PhoenixObservation:
    def __init__(self, span):
        self._span = span

    def success(self, result: ProviderResult | RunReport | None = None, *, actual_cost=None):
        from opentelemetry.trace import Status, StatusCode
        if isinstance(result, ProviderResult):
            self._span.set_attribute("output.value", _json(result.output))
            self._span.set_attribute("output.mime_type", "application/json")
            self._span.set_attribute("llm.model_name", result.reported_model)
            self._span.set_attribute("question_bank.reported_model", result.reported_model)
            self._span.set_attribute("llm.token_count.prompt", result.usage.input_tokens)
            self._span.set_attribute("llm.token_count.completion", result.usage.output_tokens)
            self._span.set_attribute("llm.token_count.total", result.usage.total_tokens)
            self._span.set_attribute("question_bank.reasoning_or_thought_tokens", result.usage.reasoning_or_thought_tokens)
        elif isinstance(result, RunReport):
            self._span.set_attribute("output.value", _json({
                "status": result.status, "stop_reason": result.stop_reason,
                "candidate_counts": result.metrics.get("candidate_counts", {}),
            }))
            self._span.set_attribute("output.mime_type", "application/json")
        elif result is not None:
            self._span.set_attribute("output.value", _json(result))
            self._span.set_attribute("output.mime_type", "application/json")
        if actual_cost is not None:
            self._span.set_attribute("question_bank.actual_cost_usd", float(actual_cost))
        self._span.set_status(Status(StatusCode.OK))

    def failure(self, failure):
        from opentelemetry.trace import Status, StatusCode
        reason = getattr(failure, "reason", type(failure).__name__)
        detail = _safe_error(getattr(failure, "detail", "") or str(failure))
        self._span.set_attribute("output.value", _json({"error_code": reason, "detail": detail}))
        self._span.set_attribute("output.mime_type", "application/json")
        self._span.set_status(Status(StatusCode.ERROR, reason))


class PhoenixObservability:
    def __init__(self, endpoint: str, project_name: str):
        from phoenix.otel import register
        self._provider = register(endpoint=endpoint, project_name=project_name,
            protocol="http/protobuf", batch=True, auto_instrument=False,
            set_global_tracer_provider=False, verbose=False)
        self._tracer = self._provider.get_tracer("question-bank-enrichment")
        self._campaign_spans = {}
        self._batch_spans = {}

    @contextmanager
    def stage(self, campaign_id: str, stage: str, node_input):
        from opentelemetry import trace

        if stage in {"campaign_status", "campaign_cancel", "campaign_resume", "command_error"}:
            with self._tracer.start_as_current_span(stage) as span:
                span.set_attribute("openinference.span.kind", "CHAIN")
                span.set_attribute("question_bank.campaign_id", campaign_id)
                span.set_attribute("input.value", _json(node_input))
                observation = _PhoenixObservation(span)
                try:
                    yield observation
                except Exception as error:
                    observation.failure(error)
                    raise
            return
        parent = self._campaign_spans.get(campaign_id)
        if parent is None:
            from opentelemetry.context import Context as OtelContext
            campaign_span = self._tracer.start_span(
                f"Campaign {campaign_id}", context=OtelContext()
            )
            campaign_span.set_attribute("openinference.span.kind", "CHAIN")
            campaign_span.set_attribute("question_bank.campaign_id", campaign_id)
            parent = (campaign_span, trace.set_span_in_context(campaign_span))
            self._campaign_spans[campaign_id] = parent
        campaign_span, campaign_context = parent
        batch_index = _nested_value(node_input, "batch_index", default=0)
        batch_key = (campaign_id, int(batch_index))
        batch_parent = self._batch_spans.get(batch_key)
        if batch_parent is None:
            batch_span = self._tracer.start_span(
                f"Batch {batch_index}", context=campaign_context
            )
            batch_span.set_attribute("openinference.span.kind", "CHAIN")
            batch_span.set_attribute("question_bank.campaign_id", campaign_id)
            batch_span.set_attribute("question_bank.batch_index", int(batch_index))
            batch_parent = (batch_span, trace.set_span_in_context(batch_span))
            self._batch_spans[batch_key] = batch_parent
        _, context = batch_parent
        with self._tracer.start_as_current_span(stage, context=context) as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("question_bank.campaign_id", campaign_id)
            span.set_attribute("question_bank.stage", stage)
            span.set_attribute("input.value", _json(node_input))
            span.set_attribute("input.mime_type", "application/json")
            observation = _PhoenixObservation(span)
            try:
                yield observation
            except Exception as error:
                observation.failure(error)
                raise

    @contextmanager
    def batch(self, request: RunRequest):
        with self._tracer.start_as_current_span(
            f"Batch {request.batch_index} / {request.idempotency_key}"
        ) as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", _json(canonical_data(request)))
            span.set_attribute("input.mime_type", "application/json")
            observation = _PhoenixObservation(span)
            try:
                yield observation
            except Exception as error:
                observation.failure(error)
                raise

    @contextmanager
    def invocation(
        self,
        invocation: ReservedInvocation,
        rendered_request: dict,
        *,
        fallback_attempt: int = 0,
    ):
        with self._tracer.start_as_current_span(invocation.role.role) as span:
            span.set_attribute("openinference.span.kind", "LLM")
            span.set_attribute("input.value", _json(rendered_request))
            span.set_attribute("input.mime_type", "application/json")
            span.set_attribute("llm.provider", invocation.role.provider)
            span.set_attribute("llm.model_name", invocation.role.model)
            span.set_attribute("question_bank.requested_model", invocation.role.model)
            span.set_attribute("question_bank.run_id", invocation.run_id)
            span.set_attribute("question_bank.invocation_id", invocation.invocation_id)
            span.set_attribute("question_bank.thinking_level", invocation.role.reasoning)
            span.set_attribute("question_bank.fallback_attempt", fallback_attempt)
            observation = _PhoenixObservation(span)
            try:
                yield observation
            except Exception as error:
                observation.failure(error)
                raise

    def close(self):
        for batch_span, _ in self._batch_spans.values():
            batch_span.end()
        self._batch_spans.clear()
        for campaign_span, _ in self._campaign_spans.values():
            campaign_span.end()
        self._campaign_spans.clear()
        self._provider.force_flush()
        self._provider.shutdown()

    def finish_campaign(self, campaign_id: str, status: str):
        for key in tuple(self._batch_spans):
            if key[0] == campaign_id:
                self.finish_batch(*key, status=status)
        parent = self._campaign_spans.pop(campaign_id, None)
        if parent is None:
            return
        campaign_span, _ = parent
        campaign_span.set_attribute("question_bank.status", status)
        campaign_span.end()
        self._provider.force_flush()

    def finish_batch(self, campaign_id: str, batch_index: int, status: str):
        parent = self._batch_spans.pop((campaign_id, int(batch_index)), None)
        if parent is None:
            return
        batch_span, _ = parent
        batch_span.set_attribute("question_bank.status", status)
        batch_span.end()


class _SafeObservation:
    def __init__(self, observation):
        self._observation = observation

    def success(self, result=None, *, actual_cost=None):
        try:
            self._observation.success(result, actual_cost=actual_cost)
        except Exception as error:
            LOGGER.warning("Phoenix trace update failed: %s", type(error).__name__)

    def failure(self, failure):
        try:
            self._observation.failure(failure)
        except Exception as error:
            LOGGER.warning("Phoenix trace update failed: %s", type(error).__name__)


class SafeObservability:
    """Keep observability failures outside the question-processing control flow."""

    def __init__(self, delegate):
        self._delegate = delegate

    @contextmanager
    def _open(self, factory):
        try:
            context = factory()
            observation = context.__enter__()
        except Exception as error:
            LOGGER.warning("Phoenix trace start failed: %s", type(error).__name__)
            yield _NoopObservation()
            return
        try:
            yield _SafeObservation(observation)
        except BaseException:
            exception = sys.exc_info()
            try:
                context.__exit__(*exception)
            except Exception as error:
                LOGGER.warning("Phoenix trace close failed: %s", type(error).__name__)
            raise
        else:
            try:
                context.__exit__(None, None, None)
            except Exception as error:
                LOGGER.warning("Phoenix trace close failed: %s", type(error).__name__)

    @contextmanager
    def batch(self, request):
        with self._open(lambda: self._delegate.batch(request)) as observation:
            yield observation

    @contextmanager
    def invocation(self, invocation, rendered_request, *, fallback_attempt=0):
        with self._open(
            lambda: self._delegate.invocation(
                invocation,
                rendered_request,
                fallback_attempt=fallback_attempt,
            )
        ) as observation:
            yield observation

    @contextmanager
    def stage(self, campaign_id, stage, node_input):
        with self._open(
            lambda: self._delegate.stage(campaign_id, stage, node_input)
        ) as observation:
            yield observation

    def close(self):
        try:
            self._delegate.close()
        except Exception as error:
            LOGGER.warning("Phoenix trace shutdown failed: %s", type(error).__name__)

    def finish_campaign(self, campaign_id, status):
        try:
            self._delegate.finish_campaign(campaign_id, status)
        except Exception as error:
            LOGGER.warning("Phoenix campaign trace close failed: %s", type(error).__name__)

    def finish_batch(self, campaign_id, batch_index, status):
        try:
            self._delegate.finish_batch(campaign_id, batch_index, status)
        except Exception as error:
            LOGGER.warning("Phoenix batch trace close failed: %s", type(error).__name__)


def _nested_value(value, key, *, default=None):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _nested_value(nested, key, default=None)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _nested_value(nested, key, default=None)
            if found is not None:
                return found
    return default


def observability_from_environment():
    endpoint = os.environ.get("QUESTION_BANK_PHOENIX_ENDPOINT", "").strip()
    if not endpoint:
        return NoopObservability()
    project = os.environ.get("QUESTION_BANK_PHOENIX_PROJECT", "question-bank-enrichment").strip()
    try:
        return SafeObservability(PhoenixObservability(endpoint, project))
    except Exception as error:
        LOGGER.warning("Phoenix tracing disabled: %s", type(error).__name__)
        return NoopObservability()
