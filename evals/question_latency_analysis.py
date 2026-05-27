"""Benchmark LLM latency for question generation.

The script runs the same prompt chain used by the game question flow:
1. Generate a canonical English ranked Candidate Set.
2. Translate the top-ranked question when the requested language is not English.

Each sample is appended to a JSONL file so partial runs still leave usable data.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from models import DEFAULT_THEMES, Level, SUPPORTED_LANGUAGES, SUPPORTED_LLM_MODELS  # noqa: E402
from services.llm_service import LLMService  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class QuestionLatencyRecord:
    sample_id: str
    created_at: str
    run_id: str
    model: str
    language: str
    theme: str
    level: str
    generation_index: int
    previous_question_count: int
    candidate_count: int
    selected_angle_keys: list[str]
    question: str
    question_en: str
    generation_seconds: float | None
    translation_seconds: float | None
    total_seconds: float
    translation_enabled: bool
    translation_model: str
    generation_error: str
    translation_error: str

    @property
    def ok(self) -> bool:
        return not self.generation_error


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure LLM latency for Who Gets You question generation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Model names to benchmark. Must be registered in SUPPORTED_LLM_MODELS.",
    )
    parser.add_argument(
        "--models-file",
        type=Path,
        default=None,
        help="Text file containing model names to benchmark, one per line. Blank lines and # comments are ignored.",
    )
    parser.add_argument(
        "--language",
        default="en",
        choices=sorted(SUPPORTED_LANGUAGES.keys()),
        help="Question language code.",
    )
    parser.add_argument(
        "--themes",
        nargs="+",
        default=[DEFAULT_THEMES[-1]],
        help="Themes to benchmark. Quote names containing spaces or emoji.",
    )
    parser.add_argument(
        "--levels",
        nargs="+",
        default=[Level.SHALLOW.value, Level.DEEP.value],
        choices=[Level.SHALLOW.value, Level.DEEP.value],
        help="Question depth levels to benchmark.",
    )
    parser.add_argument("--count", type=int, default=5, help="Samples per model/theme/level.")
    parser.add_argument("--warmup", type=int, default=0, help="Unrecorded warmup samples per model.")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Sleep between recorded samples to reduce provider-side rate-limit pressure.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / f"question_latency_{_timestamp_slug()}.jsonl",
        help="JSONL output path.",
    )
    return parser.parse_args()


def _read_models_file(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Models file does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"Models file is not a file: {path}")

    models: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            model = line.split("#", 1)[0].strip()
            if not model:
                continue
            if any(char.isspace() for char in model):
                raise SystemExit(f"Invalid model name on line {line_number} of {path}: {line.strip()}")
            models.append(model)
    if not models:
        raise SystemExit(f"Models file contains no model names: {path}")
    return models


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _resolve_models(args: argparse.Namespace) -> list[str]:
    models: list[str] = []
    if args.models_file:
        models.extend(_read_models_file(args.models_file))
    if args.models:
        models.extend(args.models)
    if not models:
        models.append(DEFAULT_MODEL)
    return _dedupe_preserve_order(models)


def _validate_models(models: Sequence[str]) -> None:
    supported = set(SUPPORTED_LLM_MODELS.keys())
    unknown = [model for model in models if model not in supported]
    if unknown:
        known = ", ".join(sorted(supported))
        raise SystemExit(f"Unsupported model(s): {', '.join(unknown)}\nKnown models: {known}")


def _generate_one(
    *,
    llm_service: LLMService,
    run_id: str,
    model: str,
    language: str,
    theme: str,
    level: str,
    generation_index: int,
    previous_questions: list[str],
    angle_history: list[str],
) -> QuestionLatencyRecord:
    created_at = datetime.now(timezone.utc).isoformat()
    total_start = time.perf_counter()
    question_en = ""
    final_question = ""
    generation_seconds: float | None = None
    translation_seconds: float | None = None
    translation_enabled = language.lower() != "en"
    generation_error = ""
    translation_error = ""
    candidate_count = 0
    selected_angle_keys: list[str] = []
    previous_question_count = len(previous_questions)

    try:
        generation_start = time.perf_counter()
        candidate_set = llm_service.generate_question_candidate_set_with_trace(
            theme=theme,
            level=Level(level),
            previous_questions=previous_questions,
            angle_history=angle_history,
        )
        generation_seconds = time.perf_counter() - generation_start
        candidate_count = len(candidate_set.candidates)
        selected_angle_keys = candidate_set.selected_angle_keys
        if not candidate_set.candidates:
            raise RuntimeError("No candidates generated")
        top_candidate = candidate_set.candidates[0]
        question_en = top_candidate.question_en.strip()
        final_question = question_en
        angle_history.extend(selected_angle_keys)
        previous_questions.extend(candidate.question_en for candidate in candidate_set.candidates)
    except Exception as exc:
        generation_error = str(exc)
        return QuestionLatencyRecord(
            sample_id=str(uuid.uuid4()),
            created_at=created_at,
            run_id=run_id,
            model=model,
            language=language,
            theme=theme,
            level=level,
            generation_index=generation_index,
            previous_question_count=previous_question_count,
            candidate_count=candidate_count,
            selected_angle_keys=selected_angle_keys,
            question=final_question,
            question_en=question_en,
            generation_seconds=generation_seconds,
            translation_seconds=translation_seconds,
            total_seconds=time.perf_counter() - total_start,
            translation_enabled=translation_enabled,
            translation_model=LLMService.TRANSLATION_MODEL if translation_enabled else "",
            generation_error=generation_error,
            translation_error=translation_error,
        )

    if translation_enabled:
        try:
            translation_start = time.perf_counter()
            translated = llm_service.translate_text_with_trace(
                text=question_en,
                source_language="en",
                target_language=language,
            )
            translation_seconds = time.perf_counter() - translation_start
            final_question = translated["text"]
            translation_error = translated["error"]
        except Exception as exc:
            translation_seconds = time.perf_counter() - translation_start
            translation_error = str(exc)

    return QuestionLatencyRecord(
        sample_id=str(uuid.uuid4()),
        created_at=created_at,
        run_id=run_id,
        model=model,
        language=language,
        theme=theme,
        level=level,
        generation_index=generation_index,
        previous_question_count=previous_question_count,
        candidate_count=candidate_count,
        selected_angle_keys=selected_angle_keys,
        question=final_question,
        question_en=question_en,
        generation_seconds=generation_seconds,
        translation_seconds=translation_seconds,
        total_seconds=time.perf_counter() - total_start,
        translation_enabled=translation_enabled,
        translation_model=LLMService.TRANSLATION_MODEL if translation_enabled else "",
        generation_error=generation_error,
        translation_error=translation_error,
    )


def _append_record(path: Path, record: QuestionLatencyRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    fraction = index - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _format_seconds(value: float) -> str:
    return f"{value:.3f}s"


def _print_summary(records: Iterable[QuestionLatencyRecord]) -> None:
    groups: dict[tuple[str, str], list[QuestionLatencyRecord]] = defaultdict(list)
    for record in records:
        groups[(record.model, record.level)].append(record)

    if not groups:
        print("No records generated.")
        return

    header = (
        f"{'model':<26} {'level':<8} {'ok':>4} {'fail':>4} "
        f"{'avg':>9} {'p50':>9} {'p95':>9} {'min':>9} {'max':>9}"
    )
    print("\nLatency summary")
    print(header)
    print("-" * len(header))
    for (model, level), group in sorted(groups.items()):
        successful = [record for record in group if record.ok]
        totals = [record.total_seconds for record in successful]
        failures = len(group) - len(successful)
        if totals:
            print(
                f"{model:<26} {level:<8} {len(successful):>4} {failures:>4} "
                f"{_format_seconds(mean(totals)):>9} "
                f"{_format_seconds(_percentile(totals, 0.50)):>9} "
                f"{_format_seconds(_percentile(totals, 0.95)):>9} "
                f"{_format_seconds(min(totals)):>9} "
                f"{_format_seconds(max(totals)):>9}"
            )
        else:
            print(f"{model:<26} {level:<8} {0:>4} {failures:>4} {'n/a':>9} {'n/a':>9} {'n/a':>9} {'n/a':>9} {'n/a':>9}")


def main() -> None:
    args = _parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    if args.warmup < 0:
        raise SystemExit("--warmup cannot be negative")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds cannot be negative")

    models = _resolve_models(args)
    _validate_models(models)

    run_id = str(uuid.uuid4())
    records: list[QuestionLatencyRecord] = []
    total_expected = len(models) * len(args.themes) * len(args.levels) * args.count
    completed = 0

    print(f"Run ID: {run_id}")
    print(f"Writing JSONL records to: {args.output}")
    print(f"Models: {', '.join(models)}")
    print(f"Recorded samples: {total_expected}")

    for model in models:
        llm_service = LLMService(llm_name=model)
        for warmup_index in range(args.warmup):
            _generate_one(
                llm_service=llm_service,
                run_id=run_id,
                model=model,
                language=args.language,
                theme=args.themes[0],
                level=args.levels[0],
                generation_index=warmup_index + 1,
                previous_questions=[],
                angle_history=[],
            )

        for theme in args.themes:
            for level in args.levels:
                history: list[str] = []
                angle_history: list[str] = []
                for index in range(1, args.count + 1):
                    record = _generate_one(
                        llm_service=llm_service,
                        run_id=run_id,
                        model=model,
                        language=args.language,
                        theme=theme,
                        level=level,
                        generation_index=index,
                        previous_questions=history,
                        angle_history=angle_history,
                    )
                    _append_record(args.output, record)
                    records.append(record)
                    completed += 1
                    status = "ok" if record.ok else "failed"
                    print(
                        f"[{completed}/{total_expected}] {model} / {theme} / {level} "
                        f"#{index}: {status}, total={_format_seconds(record.total_seconds)}"
                    )
                    if args.delay_seconds:
                        time.sleep(args.delay_seconds)

    _print_summary(records)


if __name__ == "__main__":
    main()
