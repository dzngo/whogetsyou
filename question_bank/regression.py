"""Frozen evaluator fixture support; calibration execution is separately authorized."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from question_bank.contracts import stable_hash


@dataclass(frozen=True)
class ReferenceFixture:
    cases: tuple[dict, ...]
    fixture_hash: str

    @classmethod
    def load_default(cls) -> ReferenceFixture:
        path = Path(__file__).with_name("reference_fixture_v2.json")
        cases = tuple(json.loads(path.read_text(encoding="utf-8")))
        if len(cases) != 12 or len({case["case_id"] for case in cases}) != 12:
            raise ValueError("the frozen reference fixture must contain twelve unique cases")
        return cls(cases, stable_hash(cases))

    def score(self, outcomes: dict[str, str]) -> dict:
        expected_ids = {case["case_id"] for case in self.cases}
        if set(outcomes) != expected_ids:
            raise ValueError("regression outcomes must cover the exact frozen fixture")
        mismatches = tuple(
            case["case_id"] for case in self.cases
            if outcomes[case["case_id"]] != case["expected"]
        )
        return {"fixture_hash": self.fixture_hash, "passed": not mismatches, "mismatches": mismatches}
