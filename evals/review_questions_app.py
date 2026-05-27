"""Streamlit app for human review of generated question quality."""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from models import (  # noqa: E402
    DEFAULT_THEMES,
    GENERIC_QUESTION_ANGLES,
    QUESTION_ANGLES,
    Level,
    QuestionAngle,
    SUPPORTED_LANGUAGES,
    SUPPORTED_LLM_MODELS,
)
from services import llm_prompts  # noqa: E402
from services.llm_service import LLMService  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LOCAL_TIMEZONE = ZoneInfo("Europe/Paris")
RATINGS = ["Bad", "Fine", "Very good"]
PRESET_TAGS = [
    "Nonsense",
    "Too serious",
    "Too fantasy",
    "Too childish",
    "Not realistic",
    "Too generic",
    "Off theme",
    "Too long",
    "Weird wording",
    "Repetitive",
    "Not funny",
    "Unsafe / violated",
    "Wrong language",
    "Other",
]


@dataclass
class QuestionCandidateSample:
    sample_id: str
    candidate_set_id: str
    created_at: str
    model: str
    language: str
    theme: str
    level: str
    candidate_set_index: int
    candidate_count: int
    rank: int
    angle_key: str
    question: str
    question_en: str
    generation_prompt_system: str
    generation_prompt_user: str
    translation_prompt_system: str
    translation_prompt_user: str
    translation_model: str
    translation_error: str


@dataclass(frozen=True)
class ReviewSession:
    session_id: str
    started_at: str
    results_path: Path


@st.cache_resource
def _get_review_session() -> ReviewSession:
    started = datetime.now(LOCAL_TIMEZONE)
    session_id = started.strftime("%Y%m%d_%H%M%S")
    return ReviewSession(
        session_id=session_id,
        started_at=started.isoformat(),
        results_path=RESULTS_DIR / f"question_reviews_{session_id}.jsonl",
    )


def _init_state() -> None:
    st.session_state.setdefault("question_review_samples", [])
    st.session_state.setdefault("question_review_saved_ids", set())
    st.session_state.setdefault("question_review_prompt_payload", None)
    st.session_state.setdefault("question_review_history", {})
    st.session_state.setdefault("question_review_angle_history", {})


def _language_label(code: str) -> str:
    return SUPPORTED_LANGUAGES.get(code, code)


def _preview_angles(theme: str, level: str, count: int = 5) -> List[QuestionAngle]:
    catalog = (QUESTION_ANGLES.get(theme) or {}).get(level) or GENERIC_QUESTION_ANGLES[level]
    return catalog[: min(count, len(catalog))]


def _build_prompt_payload(theme: str, level: str, language: str, previous_questions: List[str]) -> Dict[str, str]:
    del language
    return {
        "system": llm_prompts.SYSTEM_PROMPT,
        "user": llm_prompts.build_candidate_set_prompt(
            theme=theme,
            level=level,
            selected_angles=_preview_angles(theme, level),
            previous_questions=previous_questions,
        ),
    }


def _generate_samples(
    *,
    model: str,
    language: str,
    themes: List[str],
    levels: List[str],
    count: int,
    history_by_key: Dict[str, List[str]],
    angle_history_by_key: Dict[str, List[str]],
) -> List[QuestionCandidateSample]:
    llm_service = LLMService(llm_name=model)
    created_at = datetime.now(timezone.utc).isoformat()
    samples: List[QuestionCandidateSample] = []

    for theme in themes:
        for level in levels:
            history_key = f"{theme}::{level}"
            history = history_by_key.setdefault(history_key, [])
            angle_history = angle_history_by_key.setdefault(history_key, [])
            for set_index in range(1, count + 1):
                candidate_set = llm_service.generate_question_candidate_set_with_trace(
                    theme=theme,
                    level=Level(level),
                    previous_questions=history,
                    angle_history=angle_history,
                )
                candidate_set_id = str(uuid.uuid4())
                angle_history.extend(candidate_set.selected_angle_keys)
                for candidate in candidate_set.candidates:
                    question_en = candidate.question_en.strip()
                    history.append(question_en)
                    translation_trace = llm_service.translate_text_with_trace(
                        text=question_en,
                        source_language="en",
                        target_language=language,
                    )
                    samples.append(
                        QuestionCandidateSample(
                            sample_id=str(uuid.uuid4()),
                            candidate_set_id=candidate_set_id,
                            created_at=created_at,
                            model=model,
                            language=language,
                            theme=theme,
                            level=level,
                            candidate_set_index=set_index,
                            candidate_count=len(candidate_set.candidates),
                            rank=candidate.rank,
                            angle_key=candidate.angle_key,
                            question=translation_trace["text"],
                            question_en=question_en,
                            generation_prompt_system=candidate_set.generation_prompt_system,
                            generation_prompt_user=candidate_set.generation_prompt_user,
                            translation_prompt_system=translation_trace["prompt_system"],
                            translation_prompt_user=translation_trace["prompt_user"],
                            translation_model=translation_trace["model"],
                            translation_error=translation_trace["error"],
                        )
                    )

    return samples


def _append_review(record: Dict[str, object], results_path: Path) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _render_prompt_payload(payload: Dict[str, str]) -> None:
    st.markdown("### Prompt inspection")
    st.markdown("**System prompt**")
    st.code(payload["system"], language="text")
    st.markdown("**User prompt**")
    st.code(payload["user"], language="text")


def _render_sample(sample: QuestionCandidateSample, saved_ids: set[str], review_session: ReviewSession) -> None:
    saved = sample.sample_id in saved_ids
    with st.container(border=True):
        st.caption(
            f"{sample.theme} / {sample.level.title()} / {_language_label(sample.language)} / "
            f"{sample.model} / Set #{sample.candidate_set_index} / Rank {sample.rank} of {sample.candidate_count} / "
            f"Angle `{sample.angle_key}`"
        )
        st.markdown(f"**{sample.question}**")
        if sample.question_en != sample.question:
            st.caption(f"Canonical English: {sample.question_en}")
        st.caption(f"Sample ID: `{sample.sample_id}`")
        with st.expander("Generation prompt"):
            st.markdown("**System prompt**")
            st.code(sample.generation_prompt_system, language="text")
            st.markdown("**User prompt**")
            st.code(sample.generation_prompt_user, language="text")
        with st.expander("Translation prompt"):
            if not sample.translation_prompt_user:
                st.caption("No translation was needed.")
            else:
                st.markdown("**System prompt**")
                st.code(sample.translation_prompt_system, language="text")
                st.markdown("**User prompt**")
                st.code(sample.translation_prompt_user, language="text")
                if sample.translation_model:
                    st.caption(f"Translation model: `{sample.translation_model}`")
                if sample.translation_error:
                    st.warning(f"Translation failed: {sample.translation_error}")

        if saved:
            st.success("Review saved.")
            return

        rating_key = f"{sample.sample_id}_rating"
        tags_key = f"{sample.sample_id}_tags"
        other_key = f"{sample.sample_id}_other"
        comment_key = f"{sample.sample_id}_comment"

        rating = st.selectbox(
            "Rating",
            options=["Select rating", *RATINGS],
            index=0,
            key=rating_key,
        )
        tags = st.multiselect("Tags", options=PRESET_TAGS, key=tags_key)
        other_note = ""
        if "Other" in tags:
            other_note = st.text_input("Other note", key=other_key)
        comment = st.text_area("Comment", key=comment_key)

        if st.button("Save review", key=f"{sample.sample_id}_save"):
            if rating == "Select rating":
                st.error("Rating is required.")
                return
            if "Other" in tags and not other_note.strip():
                st.error("Other note is required when the Other tag is selected.")
                return

            record = {
                **asdict(sample),
                "review_session_id": review_session.session_id,
                "review_session_started_at": review_session.started_at,
                "results_path": str(review_session.results_path.relative_to(ROOT_DIR)),
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "rating": rating,
                "tags": tags,
                "other_note": other_note.strip(),
                "comment": comment.strip(),
            }
            _append_review(record, review_session.results_path)
            saved_ids.add(sample.sample_id)
            st.session_state["question_review_saved_ids"] = saved_ids
            st.success("Review saved.")
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Question Review", page_icon="?", layout="wide")
    _init_state()
    review_session = _get_review_session()

    st.title("Question Review")
    st.caption("Generate question samples and save human quality reviews without running a multiplayer game.")

    with st.sidebar:
        history_by_key = st.session_state.get("question_review_history", {})
        angle_history_by_key = st.session_state.get("question_review_angle_history", {})
        history_count = sum(len(items) for items in history_by_key.values())
        angle_history_count = sum(len(items) for items in angle_history_by_key.values())
        st.header("Review session")
        st.caption(f"Started: `{review_session.session_id}`")
        st.caption(f"Results: `{review_session.results_path.relative_to(ROOT_DIR)}`")
        st.caption(f"History: `{history_count}` generated question(s)")
        st.caption(f"Angle history: `{angle_history_count}` selected angle(s)")

        st.header("Generation")
        model = st.selectbox(
            "Model",
            options=list(SUPPORTED_LLM_MODELS.keys()),
            index=(
                list(SUPPORTED_LLM_MODELS.keys()).index("gpt-4o-mini") if "gpt-4o-mini" in SUPPORTED_LLM_MODELS else 0
            ),
            format_func=lambda code: SUPPORTED_LLM_MODELS.get(code, code),
        )
        language = st.selectbox(
            "Language",
            options=list(SUPPORTED_LANGUAGES.keys()),
            index=0,
            format_func=_language_label,
        )
        themes = st.multiselect("Themes", options=DEFAULT_THEMES, default=["Random 🎲"])
        levels = st.multiselect(
            "Levels",
            options=[Level.SHALLOW.value, Level.DEEP.value],
            default=[Level.SHALLOW.value],
            format_func=lambda value: value.title(),
        )
        count = st.number_input("Candidate sets per theme/level", min_value=1, max_value=10, value=1, step=1)

        generate = st.button("Generate questions", type="primary")
        show_prompt = st.button("Show prompt")
        clear = st.button("Clear visible samples")
        clear_history = st.button("Clear generation history")

    if clear:
        st.session_state["question_review_samples"] = []
        st.session_state["question_review_saved_ids"] = set()
        st.session_state["question_review_prompt_payload"] = None
        st.rerun()

    if clear_history:
        st.session_state["question_review_history"] = {}
        st.session_state["question_review_angle_history"] = {}
        st.session_state["question_review_prompt_payload"] = None
        st.rerun()

    if show_prompt:
        if not themes or not levels:
            st.error("Select at least one theme and one level first.")
        else:
            st.session_state["question_review_prompt_payload"] = _build_prompt_payload(
                theme=themes[0],
                level=levels[0],
                language=language,
                previous_questions=st.session_state["question_review_history"].get(f"{themes[0]}::{levels[0]}", []),
            )

    if generate:
        if not themes or not levels:
            st.error("Select at least one theme and one level.")
        else:
            try:
                with st.spinner("Generating question samples..."):
                    samples = _generate_samples(
                        model=model,
                        language=language,
                        themes=themes,
                        levels=levels,
                        count=int(count),
                        history_by_key=st.session_state["question_review_history"],
                        angle_history_by_key=st.session_state["question_review_angle_history"],
                    )
            except Exception as exc:
                st.error(f"Question generation failed: {exc}")
            else:
                st.session_state["question_review_samples"] = samples
                st.session_state["question_review_saved_ids"] = set()
                st.session_state["question_review_prompt_payload"] = None
                set_count = len({sample.candidate_set_id for sample in samples})
                st.success(f"Generated {set_count} candidate set(s), {len(samples)} candidate(s).")

    prompt_payload = st.session_state.get("question_review_prompt_payload")
    if prompt_payload:
        _render_prompt_payload(prompt_payload)

    samples = st.session_state.get("question_review_samples") or []
    if not samples:
        st.info("Generate samples from the sidebar to start reviewing.")
        return

    st.markdown("### Samples")
    saved_ids = st.session_state.get("question_review_saved_ids", set())
    for sample in samples:
        if isinstance(sample, dict):
            if "prompt_system" in sample:
                sample["generation_prompt_system"] = sample.pop("prompt_system")
                sample["generation_prompt_user"] = sample.pop("prompt_user")
                sample.setdefault("question_en", sample.get("question", ""))
                sample.setdefault("translation_prompt_system", "")
                sample.setdefault("translation_prompt_user", "")
                sample.setdefault("translation_model", "")
                sample.setdefault("translation_error", "")
            sample = QuestionCandidateSample(**sample)
        _render_sample(sample, saved_ids, review_session)

    st.caption(f"Reviews are appended to `{review_session.results_path.relative_to(ROOT_DIR)}`.")


if __name__ == "__main__":
    main()
