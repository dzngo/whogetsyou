"""Local semantic adapters and deterministic similarity evidence."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class EmbeddingAdapter(Protocol):
    model_id: str
    dimensions: int
    checksum: str

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


class HashingTestEmbedder:
    """Small deterministic test Adapter; never permitted by production manifests."""

    model_id = "hashing-test-embedder"
    dimensions = 32
    checksum = "hashing-test-v1"

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            values = [0.0] * self.dimensions
            for token in re.findall(r"[a-z0-9']+", text.lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                values[int.from_bytes(digest[:2], "big") % self.dimensions] += 1.0
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            vectors.append(tuple(value / norm for value in values))
        return vectors


class FastEmbedAdapter:
    """Pinned production embedding adapter loaded lazily to keep offline tests light."""

    model_id = "BAAI/bge-small-en-v1.5"
    dimensions = 384

    def __init__(self, *, checksum: str, model=None) -> None:
        if not checksum or checksum == "test-or-install-time-checksum":
            raise ValueError("a verified embedding artifact checksum is required")
        self.checksum = checksum
        if model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:  # pragma: no cover - optional runtime
                raise RuntimeError("install fastembed to use production embeddings") from error
            model = TextEmbedding(model_name=self.model_id)
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = [tuple(float(value) for value in vector) for vector in self._model.embed(list(texts))]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError("embedding dimensions do not match the pinned manifest")
        return vectors


def normalize_question(text: str) -> str:
    value = text.casefold().replace("’", "'")
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def token_counts(text: str) -> Counter[str]:
    return Counter(normalize_question(text).split())


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(token_counts(left))
    right_tokens = set(token_counts(right))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 1.0


def token_containment(left: str, right: str) -> float:
    left_counts = token_counts(left)
    right_counts = token_counts(right)
    denominator = min(sum(left_counts.values()), sum(right_counts.values()))
    if denominator == 0:
        return 1.0
    overlap = sum((left_counts & right_counts).values())
    return overlap / denominator


def _char_trigrams(text: str) -> Counter[str]:
    normalized = f"  {normalize_question(text)}  "
    return Counter(normalized[index : index + 3] for index in range(len(normalized) - 2))


def _counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def vector_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


@dataclass(frozen=True)
class PairMetrics:
    token_jaccard: float
    token_containment: float
    character_cosine: float
    embedding_cosine: float


def pair_metrics(
    left: str,
    right: str,
    left_vector: Sequence[float],
    right_vector: Sequence[float],
) -> PairMetrics:
    return PairMetrics(
        token_jaccard=token_jaccard(left, right),
        token_containment=token_containment(left, right),
        character_cosine=_counter_cosine(_char_trigrams(left), _char_trigrams(right)),
        embedding_cosine=vector_cosine(left_vector, right_vector),
    )


def route_pair(left: str, right: str, metrics: PairMetrics) -> str:
    if normalize_question(left) == normalize_question(right):
        return "local_reject"
    if metrics.token_jaccard >= 0.88 and metrics.character_cosine >= 0.94:
        return "local_reject"
    if metrics.token_containment >= 0.95 and metrics.character_cosine >= 0.92:
        return "local_reject"
    if (
        metrics.embedding_cosine < 0.70
        and metrics.token_jaccard <= 0.25
        and metrics.character_cosine < 0.55
    ):
        return "local_distance"
    return "gpt_review"


def select_review_pairs(pairs: Sequence[dict]) -> list[dict]:
    """Select bounded, high-signal LLM comparisons from exhaustive local evidence."""

    by_candidate: dict[str, list[dict]] = defaultdict(list)
    candidate_order: list[str] = []
    for pair in pairs:
        candidate_id = str(pair["candidate_id"])
        if candidate_id not in by_candidate:
            candidate_order.append(candidate_id)
        by_candidate[candidate_id].append(pair)

    selected: list[dict] = []
    for candidate_id in candidate_order:
        candidate_pairs = by_candidate[candidate_id]
        strongest = max(
            candidate_pairs,
            key=lambda pair: (
                float(pair["embedding_cosine"]),
                float(pair["token_containment"]),
                float(pair["character_cosine"]),
                float(pair["token_jaccard"]),
            ),
        )
        selected.append(strongest)
        selected.extend(
            pair
            for pair in candidate_pairs
            if pair is not strongest
            and (
                float(pair["token_jaccard"]) >= 0.40
                or float(pair["character_cosine"]) >= 0.65
            )
        )
    return selected
