"""Streamlit implementation of the in-game flow."""

from __future__ import annotations

import copy
import html
import random
from typing import Dict, List, Optional

import streamlit as st

from models import DEFAULT_THEMES, Level, Player, Room
from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
from storage.google_sheet_service import GoogleSheetService, GoogleSheetServiceError
from ui import common


class GameFlow:
    REFRESH_INTERVAL_SECONDS = 3
    CUSTOM_THEME_OPTION = "Custom"

    def __init__(
        self,
        room_service: RoomService,
        game_service: GameService,
        llm_service: LLMService,
    ) -> None:
        self.room_service = room_service
        self.game_service = game_service
        self.llm_service = llm_service

    def render(self) -> None:
        room_code = st.session_state.get("active_room_code")
        if not room_code:
            st.info("No active room selected. Start a game from the host lobby.")
            return
        room = self.room_service.get_room_by_code(room_code)
        if not room:
            st.warning("Room no longer exists.")
            return
        if not room.started or not room.game_state:
            st.info("Waiting for the host to start the game...")
            if st.button("Back to entry"):
                st.session_state["route"] = "entry"
                common.rerun()
            return

        state = copy.deepcopy(room.game_state or {})
        if not state:
            st.info("Initializing game state…")
            return

        profile = st.session_state.get("player_profile", {})
        current_player_id = profile.get("player_id")
        current_player_name = profile.get("name")
        is_host = current_player_id == room.host_id
        storyteller_id = self._current_storyteller_id(state)
        storyteller = self._player_lookup(room).get(storyteller_id)

        phase = state.get("phase")
        is_storyteller = current_player_id == storyteller_id
        guesses = state.get("listener_guesses", {})
        submissions = state.get("answer_submissions", {})
        listener_has_guessed = bool(current_player_id and current_player_id in guesses)
        listener_has_submitted = bool(current_player_id and current_player_id in submissions)
        waiting_phases = {
            "theme_selection",
            "level_selection",
            "question_generation",
            "reveal",
        }
        should_watch_for_updates = (not is_storyteller and phase in waiting_phases) or (
            phase == "answer_entry" and listener_has_submitted
        ) or (phase == "guessing" and (listener_has_guessed or is_storyteller))
        if should_watch_for_updates:
            self._watch_room_updates(room.room_code, room.updated_at.isoformat())

        self._render_board(
            room,
            state,
            storyteller,
            current_player_name,
            is_host,
        )

        phase = state.get("phase")
        if phase == "theme_selection":
            self._render_theme_phase(room, state, storyteller_id, current_player_id)
        elif phase == "level_selection":
            self._render_level_phase(room, state, storyteller_id, current_player_id)
        elif phase == "question_generation":
            self._render_question_phase(room, state, storyteller_id, current_player_id)
        elif phase == "answer_entry":
            self._render_answer_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "guessing":
            self._render_guess_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "reveal":
            self._render_reveal_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "results":
            self._render_results(room, state, is_host)
        else:
            st.warning("Unknown phase. Resetting to question generation.")
            state["phase"] = "question_generation"
            self._save_state(room, state)

    # ------------------------------------------------------------------ #
    # Board helpers
    # ------------------------------------------------------------------ #
    def _player_lookup(self, room: Room) -> Dict[str, Player]:
        return {player.player_id: player for player in room.players}

    def _current_storyteller_id(self, state: Dict[str, object]) -> Optional[str]:
        order = state.get("storyteller_order") or []
        if not order:
            return None
        turn_index = state.get("turn_index", 0) % len(order)
        return order[turn_index]

    def _storyteller_can_act(
        self,
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> bool:
        if not storyteller_id or not current_player_id:
            return False
        return storyteller_id == current_player_id

    def _clear_question_draft(self, room: Room, state: Dict[str, object]) -> None:
        """Discard an unconfirmed question before returning to round setup."""
        state["question"] = None
        state["question_autogen_attempted"] = False
        state["question_candidates"] = []
        state["current_candidate_index"] = 0
        question_key = f"{room.room_code}_question_text"
        st.session_state.pop(question_key, None)
        st.session_state.pop(f"{question_key}_prefill", None)

    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_room_updates(self, room_code: str, known_updated_at: str) -> None:
        """Rerun a passive game view only after another player saves a change."""
        room = self.room_service.get_room_by_code(room_code)
        if not room or room.updated_at.isoformat() != known_updated_at:
            st.rerun()

    def _render_board(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller: Optional[Player],
        current_player_name: Optional[str],
        is_host: bool,
    ) -> None:
        common.show_room_summary(room)

        st.markdown("### Scoreboard")
        with st.container(border=True):
            lookup = self._player_lookup(room)
            scoreboard = sorted((pid, score) for pid, score in (state.get("scores") or {}).items())
            scoreboard.sort(key=lambda item: item[1], reverse=True)
            for pid, score in scoreboard:
                player = lookup.get(pid)
                if not player:
                    continue
                marker = "💬" if pid == self._current_storyteller_id(state) else ""
                st.write(f"- {player.name}: **{score}** {marker}")

        st.info(f"You are playing as **{current_player_name}**")

        current_theme = state.get("selected_theme") or "To be selected"
        current_level = state.get("selected_level") or "To be selected"
        storyteller_name = storyteller.name if storyteller else "Unknown"
        st.info(
            f"**Round {state.get('round', 1)}**:  \n"
            f"Current Storyteller: **{storyteller_name}**  \n"
            f"Current theme: **{current_theme}**  \n"
            f"Current level: **{current_level}**"
        )

        if st.button("Refresh game view", key=f"{room.room_code}_refresh_view"):
            common.rerun()

        if is_host and st.button("End game", key="host_end_game"):
            self._finalize_results(room, state, manual=True)

    # ------------------------------------------------------------------ #
    # Phase renderers
    # ------------------------------------------------------------------ #
    def _render_theme_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            st.info("Waiting for the Storyteller to pick a theme...")
            return

        st.subheader("Choose theme")
        theme_key = f"{room.room_code}_theme_select"
        custom_key = f"{room.room_code}_theme_custom"
        saved_theme = str(state.get("selected_theme") or "")
        default_theme = (
            saved_theme
            if saved_theme in DEFAULT_THEMES
            else self.CUSTOM_THEME_OPTION
            if saved_theme
            else DEFAULT_THEMES[0]
        )
        if theme_key not in st.session_state:
            st.session_state[theme_key] = default_theme
        if custom_key not in st.session_state and saved_theme not in DEFAULT_THEMES:
            st.session_state[custom_key] = saved_theme
        selected = st.selectbox(
            "Select a theme",
            options=[*DEFAULT_THEMES, self.CUSTOM_THEME_OPTION],
            key=theme_key,
        )
        custom = ""
        if selected == self.CUSTOM_THEME_OPTION:
            custom = st.text_input("Custom theme", key=custom_key)
        if st.button("Confirm theme"):
            choice = custom.strip() if selected == self.CUSTOM_THEME_OPTION else selected
            if not choice:
                st.error("Please enter a custom theme.")
                return
            self._clear_question_draft(room, state)
            state["selected_theme"] = choice
            state["phase"] = "level_selection"
            self._save_state(room, state)

    def _render_level_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            st.info("Waiting for the Storyteller to pick the depth level...")
            return

        st.subheader("Choose level")
        level = st.selectbox(
            "Question depth",
            options=[Level.SHALLOW.value, Level.DEEP.value],
            format_func=lambda value: value.title(),
            key=f"{room.room_code}_level_select",
        )
        back_col, confirm_col = st.columns(2)
        if back_col.button("Back to theme", key=f"{room.room_code}_level_back"):
            self._clear_question_draft(room, state)
            state["phase"] = "theme_selection"
            self._save_state(room, state)
        if confirm_col.button("Confirm level", key=f"{room.room_code}_level_confirm"):
            self._clear_question_draft(room, state)
            state["selected_level"] = level
            state["phase"] = "question_generation"
            self._save_state(room, state)

    def _render_question_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            st.info("Waiting for the Storyteller to validate a question...")
            return

        st.subheader("Question proposal")
        current_theme = self._current_theme(state)
        current_level = self._current_level_value(state)
        question_data = state.get("question") or {}
        setup_col1, setup_col2 = st.columns(2)
        if setup_col1.button("Change theme", key=f"{room.room_code}_question_change_theme"):
            self._clear_question_draft(room, state)
            state["phase"] = "theme_selection"
            self._save_state(room, state)
        if setup_col2.button("Change level", key=f"{room.room_code}_question_change_level"):
            self._clear_question_draft(room, state)
            state["phase"] = "level_selection"
            self._save_state(room, state)
        with st.container(border=True):
            if question_data:
                st.markdown(f"**Current question:** {question_data.get('question')}")
                self._render_question_feedback_controls(
                    room=room,
                    question=question_data.get("question", ""),
                    theme=current_theme,
                    level=current_level,
                )

        manual_key = f"{room.room_code}_question_text"
        prefill_key = f"{manual_key}_prefill"
        if manual_key not in st.session_state:
            st.session_state[manual_key] = question_data.get("question", "")
        if prefill_key in st.session_state:
            st.session_state[manual_key] = st.session_state.pop(prefill_key)

        if not question_data:
            with st.spinner("Processing question ..."):
                if self._prepare_question(room, state, prefill_key, notify=False):
                    return

        manual_value = st.text_area("Edit question", key=manual_key)
        action_col1, action_col2 = st.columns(2)
        if action_col1.button("Change question", key=f"{room.room_code}_question_change"):
            with st.spinner("Processing question ..."):
                if self._prepare_question(room, state, prefill_key, notify=True, force=True):
                    return
        if action_col2.button("Rephrase question", key=f"{room.room_code}_question_rephrase"):
            cleaned = manual_value.strip()
            if not cleaned:
                st.error("Please enter a question to rephrase.")
            else:
                try:
                    with st.spinner("Rephrasing question..."):
                        new_text = self.llm_service.rephrase_text(
                            kind="question",
                            text=cleaned,
                            language=room.settings.language,
                            theme=current_theme,
                            level=current_level,
                        )
                except Exception as exc:
                    st.error(f"Content service error: {exc}")
                else:
                    st.session_state[prefill_key] = new_text
                    st.success("Question rephrased.")
                    common.rerun()

        if st.button("Confirm question"):
            final_question = manual_value.strip()
            if not final_question:
                st.error("Please enter a question.")
                return
            if room.settings.language.lower() == "en":
                final_question_en = final_question
            else:
                try:
                    with st.spinner("Saving canonical question..."):
                        translation_trace = self.llm_service.translate_text_with_trace(
                            final_question,
                            source_language=room.settings.language,
                            target_language="en",
                        )
                        if translation_trace["error"]:
                            raise RuntimeError(translation_trace["error"])
                        final_question_en = translation_trace["text"]
                except Exception as exc:
                    st.error(f"Content service error: {exc}")
                    return
            current_question_data = state.get("question") or {}
            state["question"] = {
                "question": final_question,
                "question_en": final_question_en,
                "angle_key": current_question_data.get("angle_key", ""),
                "candidate_rank": current_question_data.get("candidate_rank", 0),
            }
            history_container = state.setdefault("question_history", {})
            history_key = f"{current_theme}::{current_level}"
            if final_question_en not in history_container.setdefault(history_key, []):
                history_container[history_key].append(final_question_en)
            state["phase"] = "answer_entry"
            self._save_state(room, state)

    def _render_answer_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Submit your answer")
        question = (state.get("question") or {}).get("question")
        if not question:
            st.warning("Question not set yet.")
            return

        with st.container(border=True):
            st.markdown(f"**Question:** {question}")

        if not current_player_id:
            st.info("Waiting for your player session...")
            return

        submissions = dict(state.get("answer_submissions") or {})
        lookup = self._player_lookup(room)
        current_player = lookup.get(current_player_id)
        current_player_label = current_player.name if current_player else "Player"
        current_level = self._current_level_value(state)
        input_key = f"{room.room_code}_answer_input_{current_player_id}"
        prefill_key = f"{input_key}_prefill"
        if input_key not in st.session_state:
            st.session_state[input_key] = submissions.get(current_player_id, "")
        if prefill_key in st.session_state:
            st.session_state[input_key] = st.session_state.pop(prefill_key)

        if current_player_id == storyteller_id:
            st.caption("You are the Storyteller. Submit your answer.")
        else:
            st.caption("Submit one plausible answer. Do not reveal whether it is yours.")

        submitted = submissions.get(current_player_id, "")
        editing_key = f"{input_key}_editing"
        if not submitted:
            st.session_state.pop(editing_key, None)
        is_editing = not submitted or bool(st.session_state.get(editing_key, False))

        st.text_area("Your answer", key=input_key, disabled=not is_editing)

        if not is_editing:
            st.caption("✓ Answer submitted")
            if st.button("Modify", key=f"{room.room_code}_modify_answer_{current_player_id}"):
                st.session_state[editing_key] = True
                common.rerun()
        else:
            self._render_answer_actions(
                room=room,
                state=state,
                question=question,
                current_player_id=current_player_id,
                current_player_label=current_player_label,
                current_level=current_level,
                submissions=submissions,
                input_key=input_key,
                prefill_key=prefill_key,
                editing_key=editing_key,
                storyteller_id=storyteller_id,
            )

        pending_count = max(len(room.players) - len(submissions), 0)
        if pending_count > 0:
            st.info(f"Waiting for {pending_count} player(s) to submit answers.")
        else:
            st.info("All answers submitted. Moving to guessing...")

        if is_host and st.button("Force guessing phase", key="host_force_guessing"):
            state["multiple_choice"] = {
                "options": self._build_options_from_submissions(
                    room=room,
                    storyteller_id=storyteller_id,
                    submissions=submissions,
                )
            }
            state["listener_guesses"] = {}
            state["round_summary"] = None
            state["phase"] = "guessing"
            self._save_state(room, state)

    def _render_answer_actions(
        self,
        *,
        room: Room,
        state: Dict[str, object],
        question: str,
        current_player_id: str,
        current_player_label: str,
        current_level: str,
        submissions: Dict[str, str],
        input_key: str,
        prefill_key: str,
        editing_key: str,
        storyteller_id: Optional[str],
    ) -> None:
        col1, col2, col3 = st.columns(3)
        if col1.button("Suggest answer", key=f"{room.room_code}_suggest_answer_{current_player_id}"):
            try:
                with st.spinner("Suggesting answer..."):
                    resp = self.llm_service.suggest_answer(
                        question=question,
                        storyteller_name=current_player_label,
                        language=room.settings.language,
                        theme=self._current_theme(state),
                        level=current_level,
                        question_en=(state.get("question") or {}).get("question_en", question),
                    )
                    suggestion = (resp.answer or "").strip()
                    if not suggestion:
                        st.error("Could not generate an answer suggestion. Please try again.")
                        return
                    st.session_state[prefill_key] = suggestion
                    common.rerun()
            except Exception as exc:
                st.error(f"Content service error: {exc}")

        if col2.button("Rephrase my answer", key=f"{room.room_code}_rephrase_answer_{current_player_id}"):
            current = st.session_state.get(input_key, "").strip()
            if not current:
                st.error("Please enter an answer first.")
            else:
                try:
                    with st.spinner("Rephrasing answer..."):
                        rewritten = self.llm_service.rephrase_text(
                            kind="answer",
                            text=current,
                            language=room.settings.language,
                            question=question,
                            theme=self._current_theme(state),
                            level=current_level,
                        )
                except Exception as exc:
                    st.error(f"Content service error: {exc}")
                else:
                    st.session_state[prefill_key] = rewritten
                    common.rerun()

        submit_label = "Save changes" if current_player_id in submissions else "Submit answer"
        if col3.button(submit_label, key=f"{room.room_code}_submit_answer_{current_player_id}"):
            answer = st.session_state.get(input_key, "").strip()
            if not answer:
                st.error("Answer cannot be empty.")
                return
            other_answers = [text for pid, text in submissions.items() if pid != current_player_id and text.strip()]
            if self._is_duplicate_answer(
                candidate=answer,
                existing_answers=other_answers,
                question=question,
                language=room.settings.language,
            ):
                st.error("This answer is too similar to an existing submitted answer. Please submit a distinct one.")
                return

            submissions[current_player_id] = answer
            state["answer_submissions"] = submissions
            st.session_state.pop(editing_key, None)
            if len(submissions) >= len(room.players):
                state["multiple_choice"] = {
                    "options": self._build_options_from_submissions(
                        room=room,
                        storyteller_id=storyteller_id,
                        submissions=submissions,
                    )
                }
                state["listener_guesses"] = {}
                state["round_summary"] = None
                state["phase"] = "guessing"
            self._save_state(room, state)

    def _render_guess_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Guess the Storyteller answer")
        question = (state.get("question") or {}).get("question", "")
        with st.container(border=True):
            st.markdown(f"**Question:** {question}")

        options = state.get("multiple_choice", {}).get("options", [])
        if not options:
            st.warning("Answers are not ready yet.")
            return

        with st.container(border=True):
            st.markdown("**Answers**")
            for option in options:
                st.write(f"{option['label']}. {option['text']}")

        listeners = [player for player in room.players if player.player_id != storyteller_id]
        listener_ids = {player.player_id for player in listeners}
        guesses = dict(state.get("listener_guesses") or {})

        option_display = [f"{opt['label']}. {opt['text']}" for opt in options]
        display_to_label = {display: opt["label"] for display, opt in zip(option_display, options)}

        if current_player_id in listener_ids:
            if current_player_id in guesses:
                chosen_label = guesses[current_player_id].get("label")
                st.success(f"Your guess was submitted: {chosen_label}")
                st.info("Waiting for other listeners to submit...")
            else:
                selection_display = st.radio(
                    "Choose the Storyteller answer",
                    options=option_display,
                    index=0,
                    key=f"{room.room_code}_guess_select",
                )
                if st.button("Submit my guess"):
                    guesses[current_player_id] = {
                        "label": display_to_label[selection_display],
                    }
                    state["listener_guesses"] = guesses
                    self._save_state(room, state)
        else:
            st.info("Waiting for listeners to submit their guesses...")

        remaining_count = max(len(listeners) - len(guesses), 0)
        if remaining_count > 0:
            pending_names = [
                player.name
                for player in listeners
                if player.player_id not in guesses
            ]
            st.caption(f"Still waiting for {remaining_count} listener(s): {', '.join(pending_names)}")
        else:
            state["phase"] = "reveal"
            self._save_state(room, state)
            st.success("All guesses submitted! Revealing...")

        if is_host and st.button("Force reveal"):
            state["phase"] = "reveal"
            self._save_state(room, state)

    def _render_reveal_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Reveal & scoring")
        question = (state.get("question") or {}).get("question", "")
        with st.container(border=True):
            st.markdown(f"**Question:** {question}")

        options = (state.get("multiple_choice") or {}).get("options", [])
        lookup = self._player_lookup(room)
        with st.container(border=True):
            st.markdown("**Answers**")
            for opt in options:
                label = opt.get("label")
                text = opt.get("text", "")
                kind = opt.get("kind")
                owner_id = opt.get("owner_id")
                owner = lookup.get(owner_id) if owner_id else None
                line = f"{label}. {text}"
                if kind == "true":
                    st.markdown(
                        f"<span style='color:green; font-weight:bold'>{line}</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    if owner:
                        st.write(f"{line} — {owner.name}")
                    else:
                        st.write(line)

        if not state.get("round_summary"):
            summary = self._compute_scoring(room, state, storyteller_id)
            state["round_summary"] = summary
            self._record_completed_round(room, state, storyteller_id, summary)
            self._save_state(room, state)
        else:
            summary = state["round_summary"]

        guesses = summary.get("guesses", {})
        with st.container(border=True):
            st.markdown("**Listener guesses**")
            label_to_players: Dict[str, List[str]] = {}
            for player_id, guess in guesses.items():
                player = lookup.get(player_id)
                if not player:
                    continue
                label = guess.get("label")
                if not label:
                    continue
                label_to_players.setdefault(label, []).append(player.name)
            if not label_to_players:
                st.write("No guesses recorded.")
            else:
                for opt in options:
                    label = opt.get("label")
                    names = label_to_players.get(label)
                    if not names:
                        continue
                    st.write(f"- Option {label}: {', '.join(names)}")

        deltas = summary.get("deltas", {})
        with st.container(border=True):
            st.markdown("**Points this round**")
            for pid, delta in deltas.items():
                player = lookup.get(pid)
                if not player or delta == 0:
                    continue
                st.write(f"- {player.name}: +{delta}")

        if summary.get("winners"):
            st.success("We have a winner!")
            state["phase"] = "results"
            state["winners"] = summary["winners"]
            state["end_reason"] = (
                f"Game ended automatically because at least one player reached the target score "
                f"of {room.settings.max_score}."
            )
            self._save_state(room, state)
            return

        if (current_player_id == storyteller_id) or is_host:
            if st.button("Next turn"):
                self.game_service.prepare_next_turn(room, advance_round=True)
                common.rerun()

    def _render_results(self, room: Room, state: Dict[str, object], is_host: bool) -> None:
        lookup = self._player_lookup(room)
        self._inject_results_arcade_css()
        reason = state.get("end_reason")
        scoreboard = sorted((pid, score) for pid, score in (state.get("scores") or {}).items())
        scoreboard.sort(key=lambda item: item[1], reverse=True)

        winners = state.get("winners", [])
        winner_names = [lookup[pid].name for pid in winners if pid in lookup]
        if not winner_names and scoreboard:
            top_score = scoreboard[0][1]
            winner_names = [lookup[pid].name for pid, score in scoreboard if score == top_score and pid in lookup]

        reason_html = f"<div class='wg-results-reason'>{html.escape(str(reason))}</div>" if reason else ""
        champion_label = "Champions" if len(winner_names) > 1 else "Champion"
        champion_names = " + ".join(html.escape(name) for name in winner_names) if winner_names else "No winner"
        champion_score = max((score for _, score in scoreboard), default=0)
        ranking_html = self._build_arcade_ranking_html(scoreboard, lookup)
        stats_html = self._build_arcade_statistics_html(room, state)

        st.markdown(
            f"""
            <div class="wg-results-shell">
              <section class="wg-results-hero">
                <div class="wg-results-kicker">GAME OVER</div>
                <div class="wg-results-title">FINAL SCOREBOARD</div>
                <div class="wg-results-subtitle">Who got who?</div>
              </section>
              {reason_html}
              <section class="wg-results-champion">
                <div class="wg-results-card-label">🏆 {champion_label}</div>
                <div class="wg-results-champion-name">{champion_names}</div>
                <div class="wg-results-champion-score">{champion_score} pts</div>
              </section>
              <section class="wg-results-panel">
                <div class="wg-results-section-title">🕹️ Ranking</div>
                <div class="wg-results-ranking">
                  {ranking_html}
                </div>
              </section>
              {stats_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

        if is_host:
            if st.button("Return to host lobby"):
                self.game_service.end_game(room)
                st.session_state.pop("active_room_code", None)
                st.session_state["route"] = "host"
                common.rerun()
        else:
            if st.button("Back to entry"):
                st.session_state["route"] = "entry"
                common.rerun()

    # ------------------------------------------------------------------ #
    # Scoring & helpers
    # ------------------------------------------------------------------ #
    def _current_theme(self, state: Dict[str, object]) -> str:
        return state.get("selected_theme") or "Open conversation"

    def _current_level_value(self, state: Dict[str, object]) -> str:
        return state.get("selected_level") or Level.SHALLOW.value

    def _inject_results_arcade_css(self) -> None:
        st.markdown(
            """
            <style>
            .wg-results-shell {
              --wg-bg: #070917;
              --wg-panel: rgba(12, 18, 40, 0.92);
              --wg-panel-2: rgba(20, 29, 62, 0.9);
              --wg-cyan: #35f7ff;
              --wg-pink: #ff3df2;
              --wg-yellow: #ffe156;
              --wg-green: #54ff9f;
              --wg-text: #f6f7ff;
              --wg-muted: #9aa8d8;
              margin: 0.5rem 0 1.5rem;
              padding: clamp(1rem, 3vw, 2rem);
              border-radius: 28px;
              background:
                radial-gradient(circle at 10% 0%, rgba(53, 247, 255, 0.18), transparent 28%),
                radial-gradient(circle at 90% 10%, rgba(255, 61, 242, 0.16), transparent 30%),
                linear-gradient(135deg, #060815 0%, #101936 58%, #080a18 100%);
              border: 1px solid rgba(53, 247, 255, 0.28);
              box-shadow: 0 0 42px rgba(53, 247, 255, 0.12), inset 0 0 40px rgba(255,255,255,0.03);
              color: var(--wg-text);
              overflow: hidden;
            }
            .wg-results-hero {
              text-align: center;
              padding: 1.2rem 0 1.5rem;
              animation: wgResultsIn 520ms ease-out both;
            }
            .wg-results-kicker {
              color: var(--wg-yellow);
              letter-spacing: 0.28em;
              font-size: 0.78rem;
              font-weight: 800;
            }
            .wg-results-title {
              margin-top: 0.35rem;
              font-size: clamp(2.2rem, 8vw, 5.3rem);
              line-height: 0.92;
              font-weight: 1000;
              letter-spacing: -0.05em;
              color: #ffffff;
              text-shadow: 0 0 14px rgba(53, 247, 255, 0.75), 0 0 34px rgba(255, 61, 242, 0.4);
              animation: wgNeonPulse 2.8s ease-in-out infinite;
            }
            .wg-results-subtitle {
              margin-top: 0.7rem;
              color: var(--wg-muted);
              font-size: 1rem;
              font-weight: 600;
            }
            .wg-results-reason {
              margin: 0 auto 1rem;
              max-width: 760px;
              padding: 0.75rem 1rem;
              border: 1px solid rgba(255, 225, 86, 0.35);
              border-radius: 999px;
              color: #fff5bc;
              background: rgba(255, 225, 86, 0.08);
              text-align: center;
            }
            .wg-results-champion,
            .wg-results-panel {
              background: linear-gradient(145deg, var(--wg-panel), var(--wg-panel-2));
              border: 1px solid rgba(255, 255, 255, 0.12);
              border-radius: 24px;
              box-shadow: 0 20px 60px rgba(0, 0, 0, 0.26);
              animation: wgResultsIn 620ms ease-out both;
            }
            .wg-results-champion {
              padding: clamp(1.1rem, 3vw, 1.8rem);
              text-align: center;
              border-color: rgba(255, 225, 86, 0.52);
              box-shadow: 0 0 28px rgba(255, 225, 86, 0.12), 0 20px 60px rgba(0,0,0,0.28);
              animation: wgResultsIn 620ms ease-out both, wgWinnerPulse 3.4s ease-in-out infinite;
            }
            .wg-results-card-label,
            .wg-results-section-title {
              color: var(--wg-yellow);
              font-size: 0.88rem;
              font-weight: 900;
              letter-spacing: 0.13em;
              text-transform: uppercase;
            }
            .wg-results-champion-name {
              margin-top: 0.35rem;
              font-size: clamp(1.8rem, 5vw, 3.4rem);
              font-weight: 1000;
              color: #ffffff;
            }
            .wg-results-champion-score {
              color: var(--wg-green);
              font-weight: 900;
              font-size: 1.2rem;
            }
            .wg-results-panel {
              margin-top: 1rem;
              padding: clamp(1rem, 3vw, 1.35rem);
            }
            .wg-results-ranking {
              display: grid;
              gap: 0.7rem;
              margin-top: 0.9rem;
            }
            .wg-results-rank-row {
              display: grid;
              grid-template-columns: auto 1fr auto;
              gap: 0.9rem;
              align-items: center;
              padding: 0.85rem 1rem;
              border-radius: 18px;
              background: rgba(255,255,255,0.055);
              border: 1px solid rgba(255,255,255,0.08);
            }
            .wg-results-rank-number {
              color: var(--wg-cyan);
              font-weight: 1000;
              min-width: 2.2rem;
            }
            .wg-results-rank-name {
              color: var(--wg-text);
              font-weight: 850;
            }
            .wg-results-rank-score {
              color: var(--wg-yellow);
              font-weight: 950;
            }
            .wg-results-stat-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
              gap: 0.85rem;
              margin-top: 1rem;
            }
            .wg-results-stat-card,
            .wg-results-bestie-card {
              padding: 1rem;
              border-radius: 20px;
              background: rgba(5, 9, 24, 0.72);
              border: 1px solid rgba(53, 247, 255, 0.16);
              box-shadow: inset 0 0 18px rgba(53, 247, 255, 0.035);
            }
            .wg-results-stat-title {
              color: var(--wg-cyan);
              font-size: 1rem;
              font-weight: 950;
            }
            .wg-results-stat-subtitle {
              margin-top: 0.2rem;
              color: var(--wg-muted);
              font-size: 0.78rem;
              font-weight: 500;
            }
            .wg-results-stat-value {
              margin-top: 0.72rem;
              color: var(--wg-text);
              font-size: 1.18rem;
              font-weight: 900;
            }
            .wg-results-bestie-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
              gap: 0.85rem;
              margin-top: 1rem;
            }
            .wg-results-bestie-owner {
              color: var(--wg-yellow);
              font-size: 0.85rem;
              font-weight: 900;
            }
            .wg-results-bestie-value {
              margin-top: 0.35rem;
              color: var(--wg-text);
              font-size: 1rem;
              font-weight: 800;
            }
            .wg-results-empty {
              margin-top: 0.8rem;
              color: var(--wg-muted);
            }
            @keyframes wgResultsIn {
              from { opacity: 0; transform: translateY(14px) scale(0.985); }
              to { opacity: 1; transform: translateY(0) scale(1); }
            }
            @keyframes wgNeonPulse {
              0%, 100% { filter: brightness(1); }
              50% { filter: brightness(1.12); }
            }
            @keyframes wgWinnerPulse {
              0%, 100% { box-shadow: 0 0 24px rgba(255,225,86,0.14), 0 20px 60px rgba(0,0,0,0.28); }
              50% { box-shadow: 0 0 38px rgba(255,225,86,0.25), 0 20px 60px rgba(0,0,0,0.28); }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _build_arcade_ranking_html(
        self,
        scoreboard: List[tuple[str, int]],
        lookup: Dict[str, Player],
    ) -> str:
        rows: List[str] = []
        for index, (pid, score) in enumerate(scoreboard, start=1):
            player = lookup.get(pid)
            if not player:
                continue
            rows.append(
                "<div class='wg-results-rank-row'>"
                f"<div class='wg-results-rank-number'>#{index}</div>"
                f"<div class='wg-results-rank-name'>{html.escape(player.name)}</div>"
                f"<div class='wg-results-rank-score'>{score} pts</div>"
                "</div>"
            )
        return "".join(rows) or "<div class='wg-results-empty'>No scores recorded.</div>"

    def _build_arcade_statistics_html(self, room: Room, state: Dict[str, object]) -> str:
        stats = self._compute_game_statistics(room, state)
        if not stats["completed_round_count"]:
            return (
                "<section class='wg-results-panel'>"
                "<div class='wg-results-section-title'>📊 Game Statistics</div>"
                "<div class='wg-results-empty'>No completed rounds yet.</div>"
                "</section>"
            )
        stat_cards = [
            ("🧠 Mind Reader", "Most correct guesses", self._format_stat_winners(stats["mind_reader"], "correct guess")),
            ("🎭 Best Impostor", "Fooled the most players", self._format_stat_winners(stats["best_impostor"], "fooled guess")),
            (
                "🧩 404 Personality",
                "Hardest to guess",
                self._format_stat_winners(stats["personality_404"], "correct guess against them", lower_is_better=True),
            ),
            ("👀 No Incognito Mode", "Easiest to read", self._format_stat_winners(stats["no_incognito_mode"], "correct guess against them")),
            ("📡 Group Telepathy Score", "Correct guesses by the group", f"{stats['group_telepathy_score']:.0f}%"),
        ]
        cards_html = "".join(
            "<div class='wg-results-stat-card'>"
            f"<div class='wg-results-stat-title'>{html.escape(title)}</div>"
            f"<div class='wg-results-stat-subtitle'>{html.escape(subtitle)}</div>"
            f"<div class='wg-results-stat-value'>{html.escape(value)}</div>"
            "</div>"
            for title, subtitle, value in stat_cards
        )
        bestie_cards = "".join(
            self._build_bestie_card_html(line)
            for line in stats["certified_besties"]
        )
        return (
            "<section class='wg-results-panel'>"
            "<div class='wg-results-section-title'>⚡ Game Statistics</div>"
            f"<div class='wg-results-stat-grid'>{cards_html}</div>"
            "</section>"
            "<section class='wg-results-panel'>"
            "<div class='wg-results-section-title'>🤝 Certified Besties</div>"
            "<div class='wg-results-stat-subtitle'>Who understood each player best</div>"
            f"<div class='wg-results-bestie-grid'>{bestie_cards}</div>"
            "</section>"
        )

    def _build_bestie_card_html(self, line: str) -> str:
        owner, separator, value = line.partition(":")
        if not separator:
            owner = "Player"
            value = line
        return (
            "<div class='wg-results-bestie-card'>"
            f"<div class='wg-results-bestie-owner'>{html.escape(owner.strip())}</div>"
            f"<div class='wg-results-bestie-value'>{html.escape(value.strip())}</div>"
            "</div>"
        )

    def _compute_game_statistics(self, room: Room, state: Dict[str, object]) -> Dict[str, object]:
        lookup = self._player_lookup(room)
        completed_rounds = [item for item in state.get("completed_rounds", []) if isinstance(item, dict)]
        correct_guess_counts = {player.player_id: 0 for player in room.players}
        decoy_pick_counts = {player.player_id: 0 for player in room.players}
        storyteller_correct_counts = {player.player_id: 0 for player in room.players}
        storyteller_guess_totals = {player.player_id: 0 for player in room.players}
        bestie_counts = {
            storyteller.player_id: {listener.player_id: 0 for listener in room.players if listener.player_id != storyteller.player_id}
            for storyteller in room.players
        }
        total_guesses = 0
        total_correct = 0

        for round_record in completed_rounds:
            storyteller_id = round_record.get("storyteller_id")
            listener_ids = list(round_record.get("listener_ids") or [])
            correct_ids = set(round_record.get("correct_listener_ids") or [])
            total_guesses += len(listener_ids)
            total_correct += len(correct_ids)
            if storyteller_id in storyteller_guess_totals:
                storyteller_guess_totals[storyteller_id] += len(listener_ids)
                storyteller_correct_counts[storyteller_id] += len(correct_ids)
            for pid in correct_ids:
                if pid in correct_guess_counts:
                    correct_guess_counts[pid] += 1
                if storyteller_id in bestie_counts and pid in bestie_counts[storyteller_id]:
                    bestie_counts[storyteller_id][pid] += 1
            for pid, count in (round_record.get("decoy_picks") or {}).items():
                if pid in decoy_pick_counts:
                    decoy_pick_counts[pid] += int(count or 0)

        storyteller_rates: Dict[str, float] = {}
        for pid, guess_total in storyteller_guess_totals.items():
            if guess_total:
                storyteller_rates[pid] = storyteller_correct_counts[pid] / guess_total

        return {
            "completed_round_count": len(completed_rounds),
            "group_telepathy_score": (total_correct / total_guesses * 100) if total_guesses else 0,
            "mind_reader": self._top_stat_entries(correct_guess_counts, lookup),
            "best_impostor": self._top_stat_entries(decoy_pick_counts, lookup),
            "personality_404": self._top_stat_entries(storyteller_rates, lookup, lower_is_better=True),
            "no_incognito_mode": self._top_stat_entries(storyteller_rates, lookup),
            "certified_besties": self._build_certified_bestie_lines(room, bestie_counts),
        }

    def _top_stat_entries(
        self,
        values: Dict[str, int | float],
        lookup: Dict[str, Player],
        *,
        lower_is_better: bool = False,
    ) -> Dict[str, object]:
        meaningful = {
            pid: value
            for pid, value in values.items()
            if pid in lookup and (lower_is_better or value > 0)
        }
        if not meaningful:
            return {"names": [], "value": None}
        best_value = min(meaningful.values()) if lower_is_better else max(meaningful.values())
        names = [lookup[pid].name for pid, value in meaningful.items() if value == best_value]
        return {"names": sorted(names), "value": best_value}

    def _build_certified_bestie_lines(
        self,
        room: Room,
        bestie_counts: Dict[str, Dict[str, int]],
    ) -> List[str]:
        lookup = self._player_lookup(room)
        lines: List[str] = []
        for player in room.players:
            counts = bestie_counts.get(player.player_id) or {}
            meaningful = {pid: count for pid, count in counts.items() if count > 0 and pid in lookup}
            if not meaningful:
                lines.append(f"{player.name}: No certified bestie yet.")
                continue
            best_value = max(meaningful.values())
            names = sorted(lookup[pid].name for pid, count in meaningful.items() if count == best_value)
            suffix = "time" if best_value == 1 else "times"
            lines.append(f"{player.name}: {', '.join(names)} ({best_value} {suffix})")
        return lines

    def _format_stat_winners(
        self,
        stat: Dict[str, object],
        unit: str,
        *,
        lower_is_better: bool = False,
    ) -> str:
        names = stat.get("names") or []
        value = stat.get("value")
        if not names or value is None:
            return "Not enough data."
        if isinstance(value, float):
            value_text = f"{value * 100:.0f}%"
        else:
            suffix = unit if value == 1 else f"{unit}s"
            value_text = f"{value} {suffix}"
        qualifier = "lowest rate" if lower_is_better and isinstance(value, float) else value_text
        if lower_is_better and isinstance(value, float):
            qualifier = f"{value_text} guessed correctly"
        return f"{', '.join(names)} — {qualifier}"

    def _render_question_feedback_controls(
        self,
        *,
        room: Room,
        question: str,
        theme: str,
        level: str,
    ) -> None:
        if not question.strip():
            return
        player_profile = st.session_state.get("player_profile") or {}
        like_col, report_col = st.columns(2)
        if like_col.button("❤️ Like", key=f"{room.room_code}_like_question"):
            with st.spinner("Saving feedback ... "):
                self._submit_question_feedback(
                    player_profile=player_profile,
                    question=question,
                    theme=theme,
                    level=level,
                    action="like",
                )

        report_flag_key = f"{room.room_code}_show_report"
        if report_col.button("⚠️ Report", key=f"{room.room_code}_report_question"):
            st.session_state[report_flag_key] = not st.session_state.get(report_flag_key, False)
        if st.session_state.get(report_flag_key):
            reason_options = [
                "Weird question",
                "Doesn't match theme",
                "Doesn't match level",
                "Violent / harmful",
                "Inappropriate / offensive",
                "Other",
            ]
            reason_key = f"{room.room_code}_report_reason"
            selected_reason = st.selectbox(
                "Select a reason",
                options=reason_options,
                key=reason_key,
            )
            col_submit, col_cancel = st.columns([1, 1])
            if col_submit.button("Submit report", key=f"{room.room_code}_submit_report"):
                if selected_reason == "Select a reason":
                    st.error("Please choose a reason before submitting.")
                else:
                    with st.spinner("Saving report feedback ... "):
                        self._submit_question_feedback(
                            player_profile=player_profile,
                            question=question,
                            theme=theme,
                            level=level,
                            action="report",
                            reason=selected_reason,
                        )
                        st.session_state.pop(report_flag_key, None)
                        st.session_state.pop(reason_key, None)
                common.rerun()
            if col_cancel.button("Cancel", key=f"{room.room_code}_cancel_report"):
                st.session_state.pop(report_flag_key, None)
                st.session_state.pop(reason_key, None)
                common.rerun()

    def _submit_question_feedback(
        self,
        *,
        player_profile: Dict[str, object],
        question: str,
        theme: str,
        level: str,
        action: str,
        reason: Optional[str] = None,
    ) -> None:
        user_label = player_profile.get("name") or "Unknown player"
        try:
            GoogleSheetService().append_feedback(
                user=str(user_label),
                question=question,
                theme=theme,
                level=level,
                action=action,
                reason=reason,
            )
        except GoogleSheetServiceError as exc:
            st.error(f"Unable to record feedback: {exc}")
        except Exception as exc:
            st.error(f"Unexpected error recording feedback: {exc}")
        else:
            if action == "like":
                st.success("Thanks! Your like was recorded.")
            else:
                st.success("Report submitted. We'll review it soon.")

    def _prepare_question(
        self,
        room: Room,
        state: Dict[str, object],
        prefill_key: str,
        *,
        notify: bool,
        force: bool = False,
    ) -> bool:
        if not force and state.get("question_autogen_attempted"):
            return False
        state["question_autogen_attempted"] = True
        theme = state.get("selected_theme") or "General"
        level_value = state.get("selected_level", Level.SHALLOW.value)
        history_key = f"{theme}::{level_value}"
        candidates = list(state.get("question_candidates") or [])
        current_index = int(state.get("current_candidate_index", 0))

        if force and candidates and current_index < len(candidates) - 1:
            next_index = current_index + 1
            if self._set_current_question_from_candidate(
                room,
                state,
                prefill_key,
                candidates[next_index],
                next_index,
                history_key=history_key,
            ):
                if notify:
                    st.success("Question updated.")
                self._save_state(room, state)
                return True
            return False

        candidate_pools = state.setdefault("question_candidate_pools", {})
        pool = candidate_pools.get(history_key) or {}
        pooled_candidates = list(pool.get("candidates") or [])
        pooled_next_index = int(pool.get("next_index", 0))
        if not force and pooled_next_index < len(pooled_candidates):
            state["question_candidates"] = pooled_candidates
            if self._set_current_question_from_candidate(
                room,
                state,
                prefill_key,
                pooled_candidates[pooled_next_index],
                pooled_next_index,
                history_key=history_key,
            ):
                self._save_state(room, state)
                return True
            return False

        history_map = state.setdefault("question_history", {})
        angle_history_map = state.setdefault("angle_history", {})
        previous_questions = (history_map.get(history_key) or [])[-50:]
        previous_angles = (angle_history_map.get(history_key) or [])[-50:]
        try:
            candidate_set = self.llm_service.generate_question_candidate_set_with_trace(
                theme=theme,
                level=Level(level_value),
                previous_questions=previous_questions,
                angle_history=previous_angles,
            )
        except Exception as exc:
            self.game_service.set_state(room, state)
            st.error(f"Content service error: {exc}")
            return False

        new_candidates = [
            {
                "rank": candidate.rank,
                "angle_key": candidate.angle_key,
                "question_en": candidate.question_en,
            }
            for candidate in candidate_set.candidates
        ]
        if not new_candidates:
            st.error("Content service error: no question was generated.")
            return False
        state["question_candidates"] = new_candidates
        state["current_candidate_index"] = 0
        candidate_pools[history_key] = {
            "candidates": new_candidates,
            "next_index": 0,
        }
        if not self._set_current_question_from_candidate(
            room,
            state,
            prefill_key,
            new_candidates[0],
            0,
            history_key=history_key,
        ):
            return False

        history_container = state.setdefault("question_history", {})
        angle_history_container = state.setdefault("angle_history", {})
        question_items = history_container.setdefault(history_key, [])
        for candidate in new_candidates:
            question_en = candidate.get("question_en", "")
            if question_en and question_en not in question_items:
                question_items.append(question_en)
        angle_history_container.setdefault(history_key, []).extend(candidate_set.selected_angle_keys)
        if notify:
            st.success("Question updated.")
        self._save_state(room, state)
        return True

    def _set_current_question_from_candidate(
        self,
        room: Room,
        state: Dict[str, object],
        prefill_key: str,
        candidate: Dict[str, object],
        candidate_index: int,
        *,
        history_key: Optional[str] = None,
    ) -> bool:
        question_en = str(candidate.get("question_en") or "").strip()
        if not question_en:
            st.error("Content service error: question is empty.")
            return False
        try:
            if room.settings.language.lower() == "en":
                display_question = question_en
            else:
                translation_trace = self.llm_service.translate_text_with_trace(
                    question_en,
                    source_language="en",
                    target_language=room.settings.language,
                )
                if translation_trace["error"]:
                    raise RuntimeError(translation_trace["error"])
                display_question = translation_trace["text"]
        except Exception as exc:
            st.error(f"Content service error: {exc}")
            return False
        state["question"] = {
            "question": display_question,
            "question_en": question_en,
            "angle_key": candidate.get("angle_key", ""),
            "candidate_rank": candidate.get("rank", 0),
        }
        state["current_candidate_index"] = candidate_index
        if history_key:
            candidate_pools = state.setdefault("question_candidate_pools", {})
            pool = candidate_pools.setdefault(history_key, {})
            pool.setdefault("candidates", list(state.get("question_candidates") or []))
            pool["next_index"] = candidate_index + 1
        st.session_state[prefill_key] = display_question
        return True

    def _save_state(self, room: Room, state: Dict[str, object]) -> None:
        self.game_service.set_state(room, state)
        common.rerun()

    def _is_duplicate_answer(
        self,
        *,
        candidate: str,
        existing_answers: List[str],
        question: str,
        language: str,
    ) -> bool:
        del question, language
        if not existing_answers:
            return False
        normalized_candidate = self._normalize_answer(candidate)
        normalized_existing = {self._normalize_answer(item) for item in existing_answers}
        return normalized_candidate in normalized_existing

    @staticmethod
    def _normalize_answer(value: str) -> str:
        return " ".join(value.lower().strip().split())

    def _build_options_from_submissions(
        self,
        *,
        room: Room,
        storyteller_id: Optional[str],
        submissions: Dict[str, str],
    ) -> List[Dict[str, object]]:
        options: List[Dict[str, object]] = []
        for player in room.players:
            text = (submissions.get(player.player_id) or "").strip()
            if not text:
                continue
            kind = "true" if player.player_id == storyteller_id else "listener"
            options.append(
                {
                    "label": "",
                    "text": text,
                    "kind": kind,
                    "owner_id": player.player_id,
                }
            )
        return self._shuffle_options(options)

    def _compute_scoring(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
    ) -> Dict[str, object]:
        options = {opt["label"]: opt for opt in state.get("multiple_choice", {}).get("options", [])}
        guesses = state.get("listener_guesses", {})
        multiplier = {"shallow": 1, "deep": 2}.get(state.get("selected_level", Level.SHALLOW.value), 1)
        listeners = [player for player in room.players if player.player_id != storyteller_id]
        listener_ids = [player.player_id for player in listeners]
        correct = [pid for pid, guess in guesses.items() if options.get(guess["label"], {}).get("kind") == "true"]
        deltas = {pid: 0 for pid in state.get("scores", {})}

        if listeners:
            if len(correct) == 1:
                deltas[correct[0]] += 3 * multiplier
                if storyteller_id:
                    deltas[storyteller_id] += 3 * multiplier
            elif 0 < len(correct) < len(listeners):
                for pid in correct:
                    deltas[pid] += 1 * multiplier
                if storyteller_id:
                    deltas[storyteller_id] += 1 * multiplier
            else:
                for pid in listener_ids:
                    deltas[pid] += 2 * multiplier

            decoy_picks = {pid: 0 for pid in listener_ids}
            for guesser_id, guess in guesses.items():
                label = guess.get("label")
                owner_id = options.get(label, {}).get("owner_id")
                if owner_id in decoy_picks and owner_id != guesser_id:
                    decoy_picks[owner_id] += 1
            for pid, pick_count in decoy_picks.items():
                deltas[pid] += pick_count * multiplier
        else:
            decoy_picks = {}

        for pid, delta in deltas.items():
            state["scores"][pid] = state["scores"].get(pid, 0) + delta

        winners = [pid for pid, score in state["scores"].items() if score >= room.settings.max_score]
        return {
            "guesses": guesses,
            "deltas": deltas,
            "correct": correct,
            "winners": winners,
            "decoy_picks": decoy_picks,
        }

    def _record_completed_round(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        summary: Dict[str, object],
    ) -> None:
        completed_rounds = state.setdefault("completed_rounds", [])
        round_number = int(state.get("round", 1))
        if any(item.get("round") == round_number for item in completed_rounds if isinstance(item, dict)):
            return
        options = (state.get("multiple_choice") or {}).get("options", [])
        guesses = summary.get("guesses", {})
        correct = set(summary.get("correct", []))
        decoy_picks = summary.get("decoy_picks", {})
        completed_rounds.append(
            {
                "round": round_number,
                "storyteller_id": storyteller_id,
                "theme": state.get("selected_theme"),
                "level": state.get("selected_level"),
                "listener_ids": [player.player_id for player in room.players if player.player_id != storyteller_id],
                "guesses": copy.deepcopy(guesses),
                "correct_listener_ids": list(correct),
                "decoy_picks": copy.deepcopy(decoy_picks),
                "options": copy.deepcopy(options),
                "deltas": copy.deepcopy(summary.get("deltas", {})),
            }
        )

    def _finalize_results(self, room: Room, state: Dict[str, object], manual: bool = False) -> None:
        scores = state.get("scores", {})
        if not scores:
            return
        top_score = max(scores.values())
        winners = [pid for pid, value in scores.items() if value == top_score]
        state["phase"] = "results"
        state["winners"] = winners
        if manual:
            state["end_reason"] = "Game ended by the host."
            st.success("Game ended by host.")
        self._save_state(room, state)

    def _shuffle_options(self, options: List[Dict[str, object]]) -> List[Dict[str, object]]:
        shuffled = [dict(option) for option in options]
        random.shuffle(shuffled)
        for idx, option in enumerate(shuffled):
            option["label"] = chr(ord("A") + idx)
        return shuffled
