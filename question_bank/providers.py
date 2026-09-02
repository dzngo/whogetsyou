"""Provider invocation adapters for Question Bank Enrichment v2."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Protocol

from question_bank.contracts import ProviderResult, ReservedInvocation


class ProviderFailure(RuntimeError):
    def __init__(self, reason: str, *, ambiguous: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.ambiguous = ambiguous


class ProviderAdapter(Protocol):
    def invoke(self, invocation: ReservedInvocation) -> ProviderResult: ...


class ProviderRouter:
    def __init__(self, **providers: ProviderAdapter) -> None:
        self._providers = providers

    def invoke(self, invocation: ReservedInvocation) -> ProviderResult:
        adapter = self._providers.get(invocation.role.provider)
        if adapter is None:
            raise ProviderFailure("provider_adapter_missing", ambiguous=False)
        return adapter.invoke(invocation)


class ScriptedProvider:
    """Deterministic no-network Adapter used through the real engine seam."""

    def __init__(
        self,
        responses: Mapping[
            str,
            list[
                ProviderResult
                | ProviderFailure
                | Callable[[ReservedInvocation], ProviderResult | ProviderFailure]
            ],
        ]
        | None = None,
    ) -> None:
        self._responses: dict[
            str,
            deque[
                ProviderResult
                | ProviderFailure
                | Callable[[ReservedInvocation], ProviderResult | ProviderFailure]
            ],
        ] = defaultdict(deque)
        for role, values in (responses or {}).items():
            self._responses[role].extend(values)
        self._calls: list[ReservedInvocation] = []

    @property
    def calls(self) -> tuple[ReservedInvocation, ...]:
        return tuple(self._calls)

    def append(
        self,
        role: str,
        result: ProviderResult
        | ProviderFailure
        | Callable[[ReservedInvocation], ProviderResult | ProviderFailure],
    ) -> None:
        self._responses[role].append(result)

    def invoke(self, invocation: ReservedInvocation) -> ProviderResult:
        self._calls.append(invocation)
        queue = self._responses[invocation.role.role]
        if not queue:
            raise ProviderFailure("scripted_response_missing", ambiguous=False)
        result = queue.popleft()
        if callable(result):
            result = result(invocation)
        if isinstance(result, ProviderFailure):
            raise result
        return result


def _object(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _integer(value) -> int:
    return int(value or 0)


def _provider_failure(error: Exception) -> ProviderFailure:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    definitive = isinstance(status, int) and 400 <= status < 500 and status != 408
    return ProviderFailure(
        f"provider_{'request_rejected' if definitive else 'transport_failure'}",
        ambiguous=not definitive,
    )


def _json_schema(role: str) -> dict:
    if role.startswith("creative_"):
        return {
            "type": "object",
            "properties": {"questions": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5}},
            "required": ["questions"], "additionalProperties": False,
        }
    if role.startswith("quality_"):
        judgment = {"type": "string", "enum": ["pass", "fail", "uncertain"]}
        item = {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "clarity": judgment,
                "answerability": judgment,
                "emotional_safety": judgment,
                "level_fit": judgment,
                "deep_revelation": {
                    "type": "string",
                    "enum": ["pass", "fail", "uncertain", "not_applicable"],
                },
                "reason_codes": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "candidate_id", "clarity", "answerability", "emotional_safety",
                "level_fit", "deep_revelation", "reason_codes",
            ],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {"records": {"type": "array", "items": item}},
            "required": ["records"],
            "additionalProperties": False,
        }
    if role == "semantic_high":
        relation = {
            "type": "string",
            "enum": ["same", "overlapping", "different", "opposed", "uncertain"],
        }
        item = {
            "type": "object",
            "properties": {
                "pair_id": {"type": "string"},
                "scenario": relation,
                "perspective": relation,
                "answer_space": relation,
                "aspect": relation,
                "wording": relation,
                "verdict": {"type": "string", "enum": ["distinct", "repeat", "uncertain"]},
                "reason_codes": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "pair_id", "scenario", "perspective", "answer_space", "aspect",
                "wording", "verdict", "reason_codes",
            ],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {"pairs": {"type": "array", "items": item}},
            "required": ["pairs"],
            "additionalProperties": False,
        }
    item = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "themes": {"type": "array", "items": {"type": "string"}},
            "themes_resolved": {"type": "boolean"},
            "aspect": {"type": ["string", "null"]},
            "perspective": {"type": ["string", "null"]},
            "scenario": {"type": ["string", "null"]},
            "answer_space": {"type": ["string", "null"]},
            "wording": {"type": ["string", "null"]},
            "uncertain_fields": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "candidate_id", "themes", "themes_resolved", "aspect", "perspective",
            "scenario", "answer_space", "wording", "uncertain_fields",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"records": {"type": "array", "items": item}},
        "required": ["records"],
        "additionalProperties": False,
    }


class NativeOpenAIAdapter:
    """One-attempt OpenAI Responses adapter with native usage reconciliation."""

    def __init__(self, client=None) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:  # pragma: no cover - environment dependent
                raise RuntimeError("install the openai package to use the native adapter") from error
            client = OpenAI()
        self._client = client

    def invoke(self, invocation: ReservedInvocation) -> ProviderResult:
        role = invocation.role
        try:
            response = self._client.responses.create(
                model=role.model,
                instructions=(
                    f"Execute the {role.role} role. Return only data matching the supplied schema. "
                    "Give concise decision labels and reason codes; never reveal private reasoning."
                ),
                input=json.dumps(invocation.payload, sort_keys=True),
                reasoning={"effort": role.reasoning},
                max_output_tokens=role.output_token_limit,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": role.schema_version.replace("-", "_"),
                        "strict": True,
                        "schema": _json_schema(role.role),
                    }
                },
                prompt_cache_key=invocation.idempotency_key[:64],
                store=False,
            )
        except Exception as error:  # provider SDK types are optional
            raise _provider_failure(error) from error
        usage = _object(response, "usage")
        if usage is None:
            raise ProviderFailure("missing_provider_usage", ambiguous=True)
        input_details = _object(usage, "input_tokens_details", {})
        output_details = _object(usage, "output_tokens_details", {})
        try:
            output = json.loads(str(_object(response, "output_text", "")))
        except (TypeError, ValueError) as error:
            raise ProviderFailure("malformed_provider_json", ambiguous=True) from error
        return ProviderResult(
            output=output,
            usage=__import__("question_bank.contracts", fromlist=["ProviderUsage"]).ProviderUsage(
                _integer(_object(usage, "input_tokens", 0)),
                _integer(_object(input_details, "cached_tokens", 0)),
                _integer(_object(usage, "output_tokens", 0)),
                _integer(_object(output_details, "reasoning_tokens", 0)),
                _integer(_object(usage, "total_tokens", 0)),
            ),
            reported_model=str(_object(response, "model", "")),
            response_id=str(_object(response, "id", "")),
        )


class NativeGeminiAdapter:
    """Native Gemini adapter; hard-budget runs fail closed without a total cap."""

    def __init__(
        self, client=None, *, allow_estimated_total_generated_cap: bool = False
    ) -> None:
        if client is None:
            try:
                from google import genai
            except ImportError as error:  # pragma: no cover - environment dependent
                raise RuntimeError("install google-genai to use the native adapter") from error
            client = genai.Client()
        self._client = client
        self._allow_estimated_total_generated_cap = allow_estimated_total_generated_cap

    def invoke(self, invocation: ReservedInvocation) -> ProviderResult:
        role = invocation.role
        if (
            role.total_generated_token_limit is not None
            and not self._allow_estimated_total_generated_cap
        ):
            raise ProviderFailure("hard_generated_token_cap_unavailable", ambiguous=False)
        try:
            response = self._client.models.generate_content(
                model=role.model,
                contents=json.dumps(invocation.payload, sort_keys=True),
                config={
                    "system_instruction": (
                        f"Execute only the {role.role} role and return schema-valid JSON. "
                        "Do not include reasoning."
                    ),
                    "thinking_config": {"thinking_level": role.reasoning.upper()},
                    "max_output_tokens": (
                        role.total_generated_token_limit or role.output_token_limit
                    ),
                    "response_mime_type": "application/json",
                    "response_json_schema": _json_schema(role.role),
                },
            )
        except Exception as error:
            raise _provider_failure(error) from error
        usage = _object(response, "usage_metadata")
        if usage is None:
            raise ProviderFailure("missing_provider_usage", ambiguous=True)
        try:
            output = json.loads(str(_object(response, "text", "")))
        except (TypeError, ValueError) as error:
            raise ProviderFailure("malformed_provider_json", ambiguous=True) from error
        from question_bank.contracts import ProviderUsage

        return ProviderResult(
            output=output,
            usage=ProviderUsage(
                _integer(_object(usage, "prompt_token_count", 0)),
                _integer(_object(usage, "cached_content_token_count", 0)),
                _integer(_object(usage, "candidates_token_count", 0)),
                _integer(_object(usage, "thoughts_token_count", 0)),
                _integer(_object(usage, "total_token_count", 0)),
            ),
            reported_model=str(_object(response, "model_version", "")),
            response_id=str(_object(response, "response_id", "")),
        )
