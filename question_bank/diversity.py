"""Observed-distribution feedback with no admission or quota authority."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from question_bank.contracts import CandidateReport


@dataclass(frozen=True)
class DiversityReport:
    eligible_count: int
    distributions: dict[str, dict[str, int]]
    pending_rates: dict[str, float]
    avoid_patterns: tuple[str, ...]


def observed_diversity(candidates: tuple[CandidateReport, ...]) -> DiversityReport:
    fields = ("aspect", "perspective", "scenario", "answer_space", "wording")
    distributions: dict[str, dict[str, int]] = {
        "level": dict(Counter(item.level.value for item in candidates)),
        "themes": dict(Counter(theme for item in candidates for theme in (item.theme_memberships or ()))),
    }
    pending = {}
    patterns: list[tuple[float, str]] = []
    for field in fields:
        values = [str(item.metadata[field]) for item in candidates if item.metadata.get(field) is not None]
        counts = Counter(values)
        distributions[field] = dict(counts)
        pending[field] = 1 - (len(values) / len(candidates)) if candidates else 1.0
        if len(candidates) >= 20:
            for value, count in counts.items():
                share = count / len(values) if values else 0
                if share >= .20:
                    patterns.append((share, f"Avoid repeating {field}={value}"))
    patterns.sort(key=lambda item: (-item[0], item[1]))
    return DiversityReport(len(candidates), distributions, pending, tuple(text for _, text in patterns[:8]))
