"""Versioned public records for Question Bank Enrichment v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
USD_QUANTUM = Decimal("0.000001")


def money(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)


def canonical_data(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return canonical_data(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): canonical_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [canonical_data(item) for item in value]
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Level(str, Enum):
    SHALLOW = "shallow"
    DEEP = "deep"


class RunMode(str, Enum):
    CALIBRATION = "calibration"
    PILOT = "pilot"
    PRODUCTION = "production"


class CandidateState(str, Enum):
    PROPOSED = "proposed"
    REJECTED = "rejected"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    OPERATIONALLY_UNRESOLVED = "operationally_unresolved"
    STAGED = "staged"


@dataclass(frozen=True)
class PriceEntry:
    provider: str
    model: str
    uncached_input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    valid_through: str
    version: str


@dataclass(frozen=True)
class RoleConfiguration:
    role: str
    provider: str
    model: str
    reasoning: str
    input_token_limit: int
    output_token_limit: int
    reservation_usd: Decimal
    prompt_version: str
    schema_version: str
    total_generated_token_limit: int | None = None
    prompt_hash: str = ""
    schema_hash: str = ""
    reported_model_identities: tuple[str, ...] = ()
    fallback_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigurationManifest:
    manifest_id: str
    named_themes: tuple[str, ...]
    aspects: tuple[str, ...]
    perspectives: tuple[str, ...]
    roles: tuple[RoleConfiguration, ...]
    prices: tuple[PriceEntry, ...]
    policy_versions: Mapping[str, str]
    embedding_model: str
    embedding_dimensions: int
    embedding_checksum: str
    embedding_runtime_version: str
    embedding_normalization: str
    taxonomy_vocabulary_hash: str
    semantic_thresholds_hash: str
    reference_fixture_hash: str
    local_distance_authority: bool
    execution_version: str = "enrichment-engine-v2.5"
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def approved_defaults(
        cls,
        *,
        named_themes: Sequence[str],
        aspects: Sequence[str],
        perspectives: Sequence[str],
        embedding_checksum: str = "test-or-install-time-checksum",
        embedding_runtime_version: str = "fastembed-0.7.4",
        local_distance_authority: bool = False,
    ) -> ConfigurationManifest:
        roles = (
            *(
                RoleConfiguration(
                    role=f"creative_{strategy}",
                    provider="gemini",
                    model="gemini-3.5-flash",
                    reasoning="high",
                    input_token_limit=3000,
                    output_token_limit=1000,
                    total_generated_token_limit=3200,
                    reservation_usd=money("0.033300"),
                    prompt_version="creative-question-batch-v4-dynamic-missions",
                    schema_version="five-questions-v1",
                    fallback_models=("gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.5-flash"),
                )
                for strategy in (
                    "concrete_life_moments",
                    "relational_mirrors",
                    "tensions_tradeoffs",
                    "inner_signals",
                )
            ),
            RoleConfiguration(
                "quality_medium",
                "openai",
                "gpt-5.4-mini",
                "medium",
                4500,
                3000,
                money("0.016875"),
                "quality-medium-v3-light-shallow",
                "quality-batch-v2",
            ),
            RoleConfiguration(
                "quality_high",
                "openai",
                "gpt-5.4-mini",
                "high",
                4000,
                7000,
                money("0.034500"),
                "quality-high-v3-light-shallow",
                "quality-batch-v2",
            ),
            RoleConfiguration(
                "semantic_high",
                "openai",
                "gpt-5.4-mini",
                "high",
                6000,
                11000,
                money("0.054000"),
                "semantic-relations-v4",
                "semantic-pairs-v3",
            ),
            RoleConfiguration(
                "observed_diversity", "gemini", "gemini-3.5-flash", "high",
                6000, 2000, money("0.045000"), "observed-diversity-missions-v2",
                "diversity-missions-v2", total_generated_token_limit=4000,
                fallback_models=("gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.5-flash"),
            ),
            RoleConfiguration(
                "metadata_medium",
                "openai",
                "gpt-5.4-mini",
                "medium",
                4500,
                4500,
                money("0.023625"),
                "metadata-v2",
                "metadata-batch-v3",
            ),
        )
        roles = tuple(
            replace(
                role,
                prompt_hash=stable_hash(
                    {"role": role.role, "prompt_version": role.prompt_version}
                ),
                schema_hash=stable_hash(
                    {"role": role.role, "schema_version": role.schema_version}
                ),
                reported_model_identities=(
                    (role.model, "gpt-5.4-mini-2026-03-17")
                    if role.provider == "openai"
                    else (role.model,)
                ),
            )
            for role in roles
        )
        prices = (
            PriceEntry("gemini", "gemini-3-flash-preview", money("0.50"), money("0.05"), money("3.00"), "2026-12-31", "prices-2026-09-04"),
            PriceEntry("gemini", "gemini-3.6-flash", money("0.75"), money("0.075"), money("3.75"), "2026-12-31", "prices-2026-09-04"),
            PriceEntry(
                "gemini",
                "gemini-3.5-flash",
                money("1.50"),
                money("0.15"),
                money("9.00"),
                "2026-12-31",
                "prices-2026-09-01",
            ),
            PriceEntry(
                "openai",
                "gpt-5.4-mini",
                money("0.75"),
                money("0.075"),
                money("4.50"),
                "2026-12-31",
                "prices-2026-09-01",
            ),
        )
        policies = {
            "quality": "quality-v4-light-shallow",
            "diversity": "gemini-dynamic-missions-v2",
            "gemini_fallback": "503-only-1-2-4-seconds-v1",
            "admission": "admission-v2",
            "semantic": "semantic-routing-v5",
            "metadata": "metadata-v2",
            "review": "review-v2",
            "release": "release-v2",
            "source_permission": "source-permission-v2",
        }
        canonical_themes = tuple(sorted(set(named_themes)))
        canonical_aspects = tuple(sorted(set(aspects)))
        canonical_perspectives = tuple(sorted(set(perspectives)))
        fixture_path = Path(__file__).with_name("reference_fixture_v2.json")
        fixture_cases = tuple(json.loads(fixture_path.read_text(encoding="utf-8")))
        threshold_policy = {
            "exact_normalization": "unicode-casefold-apostrophe-word-space-v1",
            "near_copy": {"jaccard": 0.88, "character_cosine": 0.94},
            "containment_copy": {"containment": 0.95, "character_cosine": 0.92},
            "local_distance": {
                "embedding_cosine_lt": 0.70,
                "jaccard_lte": 0.25,
                "character_cosine_lt": 0.55,
            },
            "review_selection": {
                "strongest_neighbor_per_candidate": 1,
                "lexical_alert_jaccard_gte": 0.40,
                "lexical_alert_character_cosine_gte": 0.65,
                "maximum_pairs": 24,
                "pairs_per_call": 6,
            },
        }
        payload = {
            "named_themes": canonical_themes,
            "aspects": canonical_aspects,
            "perspectives": canonical_perspectives,
            "roles": roles,
            "prices": prices,
            "policy_versions": policies,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "embedding_dimensions": 384,
            "embedding_checksum": embedding_checksum,
            "embedding_runtime_version": embedding_runtime_version,
            "embedding_normalization": "l2-normalized-float32-v1",
            "taxonomy_vocabulary_hash": stable_hash(
                {
                    "themes": canonical_themes,
                    "aspects": canonical_aspects,
                    "perspectives": canonical_perspectives,
                }
            ),
            "semantic_thresholds_hash": stable_hash(threshold_policy),
            "reference_fixture_hash": stable_hash(fixture_cases),
            "local_distance_authority": local_distance_authority,
            "execution_version": "enrichment-engine-v2.10-single-level-campaigns",
            "schema_version": SCHEMA_VERSION,
        }
        return cls(manifest_id=f"config-{stable_hash(payload)[:24]}", **payload)

    def role(self, name: str) -> RoleConfiguration:
        for role in self.roles:
            if role.role == name:
                return role
        raise KeyError(name)

    def validate_content_address(self) -> None:
        payload = canonical_data(self)
        manifest_id = payload.pop("manifest_id")
        expected = f"config-{stable_hash(payload)[:24]}"
        if manifest_id != expected:
            raise ValueError("configuration manifest content hash does not match its id")
        if any(
            not role.prompt_hash
            or not role.schema_hash
            or not role.reported_model_identities
            for role in self.roles
        ):
            raise ValueError("configuration manifest is missing prompt or schema hashes")
        prices = {(item.provider, item.model): item for item in self.prices}
        for role in self.roles:
            for model in role.fallback_models:
                if role.provider != "gemini" or (role.provider, model) not in prices:
                    raise ValueError("fallback model is missing a Gemini price entry")
                fallback_price = prices[(role.provider, model)]
                fallback_bound = money((Decimal(role.input_token_limit) * fallback_price.uncached_input_per_million
                    + Decimal(role.total_generated_token_limit or 0) * fallback_price.output_per_million) / Decimal(1_000_000))
                if role.reservation_usd < fallback_bound:
                    raise ValueError("fallback reservation is below its worst-case bound")
            price = prices.get((role.provider, role.model))
            if price is None:
                raise ValueError(f"price catalog is missing {role.provider}/{role.model}")
            generated_limit = (
                role.total_generated_token_limit
                if role.provider == "gemini"
                else role.output_token_limit
            )
            if generated_limit is None:
                raise ValueError(f"{role.role} has no finite generated-token bound")
            worst_case = money(
                Decimal(role.input_token_limit)
                * price.uncached_input_per_million
                / Decimal(1_000_000)
                + Decimal(generated_limit)
                * price.output_per_million
                / Decimal(1_000_000)
            )
            if role.reservation_usd < worst_case:
                raise ValueError(f"{role.role} reservation is below its worst-case bound")
        fixture_path = Path(__file__).with_name("reference_fixture_v2.json")
        current_fixture_hash = stable_hash(
            tuple(json.loads(fixture_path.read_text(encoding="utf-8")))
        )
        if self.reference_fixture_hash != current_fixture_hash:
            raise ValueError("configuration manifest references a stale regression fixture")

    @property
    def creative_roles(self) -> tuple[RoleConfiguration, ...]:
        return tuple(role for role in self.roles if role.role.startswith("creative_"))


@dataclass(frozen=True)
class RunRequest:
    idempotency_key: str
    mode: RunMode
    snapshot_id: str
    candidate_target: int
    levels: tuple[Level, ...]
    authorization_usd: Decimal
    attempt_limit: int
    uncertainty_review_limit: int
    protected_spot_check_count: int
    configuration_id: str = ""
    batch_index: int = 0
    comparison_candidate_ids: tuple[str, ...] = ()

    @classmethod
    def pilot(
        cls,
        *,
        idempotency_key: str,
        snapshot_id: str,
        authorization_usd: Decimal = Decimal("0.20"),
        configuration_id: str = "",
        batch_index: int = 0,
    ) -> RunRequest:
        return cls(
            idempotency_key=idempotency_key,
            mode=RunMode.PILOT,
            snapshot_id=snapshot_id,
            candidate_target=20,
            levels=(Level.SHALLOW, Level.DEEP),
            authorization_usd=money(authorization_usd),
            attempt_limit=12,
            uncertainty_review_limit=1,
            protected_spot_check_count=4,
            configuration_id=configuration_id,
            batch_index=batch_index,
        )

    @classmethod
    def production_batch(
        cls,
        *,
        idempotency_key: str,
        snapshot_id: str,
        batch_index: int,
        authorization_usd: Decimal = Decimal("2.00"),
        attempt_limit: int = 100,
        uncertainty_review_limit: int = 6,
        protected_spot_check_count: int = 4,
        configuration_id: str = "",
        levels: tuple[Level, ...] = (Level.SHALLOW, Level.DEEP),
        comparison_candidate_ids: tuple[str, ...] = (),
    ) -> RunRequest:
        return cls(
            idempotency_key=idempotency_key,
            mode=RunMode.PRODUCTION,
            snapshot_id=snapshot_id,
            candidate_target=20,
            levels=levels,
            authorization_usd=money(authorization_usd),
            attempt_limit=attempt_limit,
            uncertainty_review_limit=uncertainty_review_limit,
            protected_spot_check_count=protected_spot_check_count,
            configuration_id=configuration_id,
            batch_index=batch_index,
            comparison_candidate_ids=comparison_candidate_ids,
        )


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_or_thought_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ReservedInvocation:
    run_id: str
    invocation_id: str
    idempotency_key: str
    role: RoleConfiguration
    payload: Mapping[str, Any]
    reservation_id: str


@dataclass(frozen=True)
class ProviderResult:
    output: Mapping[str, Any]
    usage: ProviderUsage
    reported_model: str
    response_id: str


@dataclass(frozen=True)
class CandidateReport:
    candidate_id: str
    text: str
    level: Level
    strategy: str
    state: CandidateState
    reason_codes: tuple[str, ...] = ()
    theme_memberships: tuple[str, ...] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LedgerSummary:
    authorized_usd: Decimal
    reconciled_usd: Decimal
    active_reserved_usd: Decimal
    unknown_usd: Decimal
    remaining_usd: Decimal


@dataclass(frozen=True)
class RunReport:
    run_id: str
    request_id: str
    status: str
    stop_reason: str
    candidates: tuple[CandidateReport, ...]
    attempts: int
    cache_hits: int
    ledger: LedgerSummary
    configuration_id: str
    snapshot_id: str
    review_case_ids: tuple[str, ...] = ()
    resumable: bool = False
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseReport:
    snapshot_id: str
    passed: bool
    blockers: tuple[str, ...]
    question_ids: tuple[str, ...]
    manifest_hash: str = ""


@dataclass(frozen=True)
class ReleasePointerEvent:
    event_id: str
    action: str
    snapshot_id: str | None
    previous_snapshot_id: str | None
