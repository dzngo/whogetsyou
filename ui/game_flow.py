"""Streamlit implementation of the in-game flow."""

from __future__ import annotations

import copy
import random
from typing import Dict, List, Optional

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from models import DEFAULT_THEMES, Level, Player, Room
from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
from storage.google_sheet_service import GoogleSheetService, GoogleSheetServiceError
from ui import common


class GameFlow:
    def __init__(
        self,
        room_service: RoomService,
        game_service: GameService,
        llm_service: LLMService,
    ) -> None:
        self.room_service = room_service
        self.game_service = game_service
        self.llm_service = llm_service
        model_name = getattr(getattr(llm_service, "_llm", None), "model_name", "gemini-2.5-flash")
        self.validation_llm_service = LLMService(llm_name=model_name)

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
        if (not is_storyteller and phase in waiting_phases) or (
            phase == "answer_entry" and listener_has_submitted
        ) or (phase == "guessing" and listener_has_guessed):
            st_autorefresh(interval=1000, key=f"game_auto_refresh_wait_{room.room_code}")
        if is_storyteller and phase == "guessing":
            st_autorefresh(interval=1000, key=f"game_auto_refresh_storyteller_{room.room_code}_{phase}")

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
        options = DEFAULT_THEMES
        selected = st.selectbox(
            "Select a theme",
            options=options,
            key=f"{room.room_code}_theme_select",
        )
        custom = st.text_input(
            "Or enter a custom theme",
            key=f"{room.room_code}_theme_custom",
        )
        if st.button("Confirm theme"):
            choice = custom.strip() or selected
            if not choice:
                st.error("Please choose or enter a theme.")
                return
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
        if st.button("Confirm level"):
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
            if self._prepare_question(room, state, prefill_key, notify=False):
                return

        manual_value = st.text_area("Edit question", key=manual_key)
        action_col1, action_col2 = st.columns(2)
        if action_col1.button("Change question", key=f"{room.room_code}_question_change"):
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
            state["question"] = {"question": final_question}
            history_container = state.setdefault("question_history", {})
            if isinstance(history_container, list):
                history_container = {"__legacy__": history_container}
                state["question_history"] = history_container
            history_key = f"{current_theme}::{current_level}"
            history_container.setdefault(history_key, []).append(final_question)
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
            st.caption("You are the Storyteller. Submit your true answer.")
        else:
            st.caption("Submit one plausible answer. Do not reveal if it is true or not.")

        st.text_area("Your answer", key=input_key)

        submitted = submissions.get(current_player_id, "")
        if submitted:
            with st.container(border=True):
                st.markdown("**Submitted answer**")
                st.write(submitted)

        col1, col2, col3 = st.columns(3)
        if col1.button("Suggest answer", key=f"{room.room_code}_suggest_answer_{current_player_id}"):
            try:
                with st.spinner("Suggesting answer..."):
                    resp = self.llm_service.suggest_answer(
                        question=question,
                        storyteller_name=current_player_label,
                        gameplay_mode="simple",
                        language=room.settings.language,
                        theme=self._current_theme(state),
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

        if col3.button("Submit answer", key=f"{room.room_code}_submit_answer_{current_player_id}"):
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

    def _render_guess_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Guess the storyteller's true answer")
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
                    "Choose the storyteller's true answer",
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
            st.caption(f"Still waiting for {remaining_count} listener(s).")
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
        st.subheader("Final results")
        lookup = self._player_lookup(room)
        reason = state.get("end_reason")
        if reason:
            st.info(reason)

        winners = state.get("winners", [])
        if winners:
            names = ", ".join(lookup[pid].name for pid in winners if pid in lookup)
            st.success(f"Winner(s): {names}")
        scoreboard = sorted((pid, score) for pid, score in (state.get("scores") or {}).items())
        scoreboard.sort(key=lambda item: item[1], reverse=True)
        st.markdown("### Final scoreboard")
        with st.container(border=True):
            for pid, score in scoreboard:
                player = lookup.get(pid)
                if not player:
                    continue
                st.write(f"- {player.name}: **{score}**")

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
        history_map = state.get("question_history") or {}
        if isinstance(history_map, list):
            history_map = {"__legacy__": history_map}
            state["question_history"] = history_map
        theme = state.get("selected_theme") or "General"
        level_value = state.get("selected_level", Level.SHALLOW.value)
        history_key = f"{theme}::{level_value}"
        previous_questions = (history_map.get(history_key) or [])[-50:]
        try:
            with st.spinner("Preparing a fresh question..."):
                resp = self.llm_service.generate_question(
                    theme=theme,
                    level=Level(level_value),
                    previous_questions=previous_questions,
                    language=room.settings.language,
                )
        except Exception as exc:
            self.game_service.set_state(room, state)
            st.error(f"Content service error: {exc}")
            return False
        payload = resp.model_dump()
        state["question"] = payload
        history_container = state.setdefault("question_history", {})
        if isinstance(history_container, list):
            history_container = {"__legacy__": history_container}
            state["question_history"] = history_container
        history_container.setdefault(history_key, []).append(payload["question"])
        st.session_state[prefill_key] = payload["question"]
        if notify:
            st.success("Question updated.")
        self._save_state(room, state)
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
        if not existing_answers:
            return False
        normalized_candidate = self._normalize_answer(candidate)
        normalized_existing = {self._normalize_answer(item) for item in existing_answers}
        if normalized_candidate in normalized_existing:
            return True
        try:
            resp = self.validation_llm_service.check_duplicate_answer(
                candidate_answer=candidate,
                existing_answers=existing_answers,
                question=question,
                language=language,
            )
            return bool(resp.is_duplicate)
        except Exception:
            return False

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
