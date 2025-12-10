"""Streamlit implementation of the in-game flow."""

from __future__ import annotations

import copy
import random
from typing import Dict, List, Optional

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from models import (
    DEFAULT_THEMES,
    GameplayMode,
    Level,
    LevelMode,
    Player,
    Room,
    ThemeMode,
)
from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
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
        is_listener = current_player_id and current_player_id != storyteller_id
        listener_has_guessed = bool(is_listener and current_player_id in guesses)
        waiting_phases = {
            "theme_selection",
            "level_selection",
            "question_generation",
            "answer_entry",
            "options",
            "reveal",
        }
        # Listeners auto-refresh during waiting phases, and after they have submitted a guess.
        if (not is_storyteller and phase in waiting_phases) or (
            not is_storyteller and phase == "guessing" and listener_has_guessed
        ):
            st_autorefresh(interval=1000, key=f"game_auto_refresh_wait_{room.room_code}")
        # Storyteller auto-refreshes during guessing to see incoming choices
        if is_storyteller and phase == "guessing":
            st_autorefresh(interval=1000, key=f"game_auto_refresh_guess_{room.room_code}")

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
            self._render_answer_phase(room, state, storyteller_id, current_player_id)
        elif phase == "options":
            self._render_options_phase(room, state, storyteller_id, current_player_id)
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
        st.markdown(
            """
            <style>
            div.stAlert {
                text-align: center;
            }
            div.stAlert p {
                text-align: center;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.info(f"You are playing as **{current_player_name}**")

        current_theme = state.get("selected_theme") or (
            "To be selected" if room.settings.theme_mode == ThemeMode.DYNAMIC else "Static rotation"
        )
        current_level = state.get("selected_level") or (
            "To be selected" if room.settings.level_mode == LevelMode.DYNAMIC else "Static"
        )
        storyteller_name = storyteller.name if storyteller else "Unknown"
        st.info(
            f"**Round {state.get('round', 1)}**:  \n"
            f"Current Storyteller: **{storyteller_name}**  \n"
            f"Current theme: **{current_theme}**  \n"
            f"Current level: **{current_level}**"
        )

        if st.button("Refresh game view", key=f"{room.room_code}_refresh_view"):
            common.rerun()

        if is_host:
            if st.button("End game", key="host_end_game"):
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
        if room.settings.theme_mode == ThemeMode.STATIC:
            theme = state.get("selected_theme") or (
                room.settings.selected_themes[0] if room.settings.selected_themes else "Open conversation"
            )
            st.info(f"Static theme confirmed: **{theme}**")
            state["selected_theme"] = theme
            next_phase = "level_selection" if room.settings.level_mode == LevelMode.DYNAMIC else "question_generation"
            state["phase"] = next_phase
            self._save_state(room, state)
            return

        options = sorted(set(DEFAULT_THEMES + room.settings.selected_themes))
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
            state["phase"] = (
                "level_selection" if room.settings.level_mode == LevelMode.DYNAMIC else "question_generation"
            )
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
        if room.settings.level_mode == LevelMode.STATIC:
            level = room.settings.selected_level.value if room.settings.selected_level else Level.SHALLOW.value
            st.info(f"Static level confirmed: **{level.title()}**")
            state["selected_level"] = level
            state["phase"] = "question_generation"
            self._save_state(room, state)
            return

        level = st.selectbox(
            "Question depth",
            options=[Level.SHALLOW.value, Level.MEDIUM.value, Level.DEEP.value],
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
        if can_act:
            st.subheader("Question proposal")
        current_theme = self._current_theme(room, state)
        current_level = self._current_level_value(room, state)
        question_data = state.get("question") or {}
        if question_data:
            st.markdown(f"**Current question:** {question_data.get('question')}")

        if not can_act:
            st.info("Waiting for the Storyteller to validate a question...")
            return

        manual_key = f"{room.room_code}_question_text"
        prefill_key = f"{manual_key}_prefill"
        if manual_key not in st.session_state:
            st.session_state[manual_key] = question_data.get("question", "")
        if prefill_key in st.session_state:
            st.session_state[manual_key] = st.session_state.pop(prefill_key)

        if not question_data:
            if self._prepare_question(room, state, prefill_key, notify=False):
                return

        manual_value = st.text_area(
            "Edit question",
            key=manual_key,
        )
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
            state.setdefault("question_history", []).append(final_question)
            state["phase"] = "answer_entry"
            self._save_state(room, state)

    def _render_answer_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        st.subheader("Storyteller answers")
        question = (state.get("question") or {}).get("question")
        if not question:
            st.warning("Question not set yet.")
            return
        st.markdown(f"**Question:** {question}")

        current_theme = self._current_theme(room, state)
        current_level = self._current_level_value(room, state)
        if not can_act:
            st.info("Waiting for the Storyteller to confirm their answers...")
            return
        true_key = f"{room.room_code}_true_answer"
        true_prefill_key = f"{true_key}_prefill"
        trap_key = f"{room.room_code}_trap_answer"
        trap_prefill_key = f"{trap_key}_prefill"
        if true_key not in st.session_state:
            st.session_state[true_key] = state.get("true_answer") or ""
        if true_prefill_key in st.session_state:
            st.session_state[true_key] = st.session_state.pop(true_prefill_key)
        lookup = self._player_lookup(room)
        storyteller_obj = lookup.get(storyteller_id) if storyteller_id else None
        storyteller_name = storyteller_obj.name if storyteller_obj else "Storyteller"
        st.text_area(
            "True answer",
            key=true_key,
            disabled=not can_act,
        )
        true_actions = st.columns(2)
        if true_actions[0].button("Suggest honest answer", key=f"{room.room_code}_suggest_true"):
            try:
                with st.spinner("Suggesting an honest answer..."):
                    resp = self.llm_service.suggest_true_answer(
                        question=question,
                        storyteller_name=storyteller_name,
                        gameplay_mode=room.settings.gameplay_mode,
                        language=room.settings.language,
                    )
                st.session_state[true_prefill_key] = resp.answer
                st.success("True answer suggested.")
            except Exception as exc:
                st.error(f"Content service error: {exc}")
            else:
                common.rerun()
        if true_actions[1].button("Rephrase true answer", key=f"{room.room_code}_rephrase_true"):
            current = st.session_state.get(true_key, "").strip()
            if not current:
                st.error("Enter a true answer before rephrasing.")
            else:
                try:
                    with st.spinner("Rephrasing true answer..."):
                        rewritten = self.llm_service.rephrase_text(
                            kind="true answer",
                            text=current,
                            language=room.settings.language,
                            question=question,
                            theme=current_theme,
                            level=current_level,
                        )
                    st.session_state[true_prefill_key] = rewritten
                    st.success("True answer rephrased.")
                except Exception as exc:
                    st.error(f"Content service error: {exc}")
                else:
                    common.rerun()

        if room.settings.gameplay_mode == GameplayMode.BLUFFING:
            if trap_key not in st.session_state:
                st.session_state[trap_key] = state.get("trap_answer") or ""
            if trap_prefill_key in st.session_state:
                st.session_state[trap_key] = st.session_state.pop(trap_prefill_key)
            st.text_area(
                "Trap answer",
                key=trap_key,
                disabled=not can_act,
            )
            trap_actions = st.columns(2)
            if trap_actions[0].button("Suggest trap answer", key=f"{room.room_code}_suggest_trap"):
                try:
                    with st.spinner("Suggesting a trap answer..."):
                        resp = self.llm_service.suggest_trap_answer(
                            question=question,
                            true_answer=st.session_state.get(true_key, state.get("true_answer", "")),
                            storyteller_name=storyteller_name,
                            language=room.settings.language,
                        )
                    st.session_state[trap_prefill_key] = resp.answer
                    st.success("Trap answer suggested.")
                except Exception as exc:
                    st.error(f"Content service error: {exc}")
                else:
                    common.rerun()
            if trap_actions[1].button("Rephrase trap answer", key=f"{room.room_code}_rephrase_trap"):
                current = st.session_state.get(trap_key, "").strip()
                if not current:
                    st.error("Enter a trap answer before rephrasing.")
                else:
                    try:
                        with st.spinner("Rephrasing trap answer..."):
                            rewritten = self.llm_service.rephrase_text(
                                kind="trap answer",
                                text=current,
                                language=room.settings.language,
                                question=question,
                                theme=current_theme,
                                level=current_level,
                            )
                        st.session_state[trap_prefill_key] = rewritten
                        st.success("Trap answer rephrased.")
                    except Exception as exc:
                        st.error(f"Content service error: {exc}")
                    else:
                        common.rerun()

        if st.button("Confirm answers"):
            true_answer = st.session_state.get(true_key, "").strip()
            if not true_answer:
                st.error("True answer cannot be empty.")
                return
            trap_answer = None
            if room.settings.gameplay_mode == GameplayMode.BLUFFING:
                trap_answer = st.session_state.get(trap_key, "").strip()
                if not trap_answer:
                    st.error("Trap answer is required in Bluffing mode.")
                    return
            state["true_answer"] = true_answer
            state["trap_answer"] = trap_answer
            state["phase"] = "options"
            self._save_state(room, state)

    def _render_options_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
    ) -> None:
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if can_act:
            st.subheader("Build multiple choice options")
        current_theme = self._current_theme(room, state)
        current_level = self._current_level_value(room, state)
        question = (state.get("question") or {}).get("question", "")
        if question:
            st.markdown(f"**Question:** {question}")

        multiple_choice = state.get("multiple_choice") or {}
        options = multiple_choice.get("options", [])

        if not can_act:
            st.info("Waiting for the Storyteller to confirm the multiple choices options...")
            return

        if not options and state.get("true_answer"):
            if self._prepare_options(room, state):
                return

        options = (state.get("multiple_choice") or {}).get("options", [])
        if not options:
            st.warning("Options not ready yet.")
            return

        st.markdown("**Current options:**")
        for option in options:
            label = option.get("label")
            kind = option.get("kind")
            key = f"{room.room_code}_option_{label}"
            prefill_key = f"{key}_prefill"
            if key not in st.session_state:
                st.session_state[key] = option.get("text", "")
            if prefill_key in st.session_state:
                st.session_state[key] = st.session_state.pop(prefill_key)

            col_text, col_btn = st.columns([4, 2])
            with col_text:
                st.text_area(
                    f"{label} ({kind})",
                    key=key,
                )
            with col_btn:
                if st.button("Regenerate", key=f"{key}_regen"):
                    try:
                        with st.spinner("Regenerating option..."):
                            new_text = self.llm_service.refine_option_text(
                                question=question,
                                true_answer=state.get("true_answer", ""),
                                kind=kind,
                                current_text=st.session_state.get(key, ""),
                                trap_answer=state.get("trap_answer"),
                                language=room.settings.language,
                            )
                            if new_text:
                                st.session_state[prefill_key] = new_text
                                st.success("Option updated.")
                                common.rerun()
                    except Exception as exc:
                        st.error(f"Content service error: {exc}")
                if st.button("Rephrase", key=f"{key}_rephrase"):
                    current = st.session_state.get(key, "").strip()
                    if not current:
                        st.error("Enter option text before rephrasing.")
                    else:
                        try:
                            with st.spinner("Rephrasing option..."):
                                updated = self.llm_service.rephrase_text(
                                    kind=f"option {label}",
                                    text=current,
                                    question=question,
                                    language=room.settings.language,
                                    theme=current_theme,
                                    level=current_level,
                                )
                            st.session_state[prefill_key] = updated
                            st.success("Option rephrased.")
                        except Exception as exc:
                            st.error(f"Content service error: {exc}")
                        else:
                            common.rerun()

        if can_act and st.button("Confirm options & invite guesses"):
            # Persist any manual edits back to the game state.
            for option in options:
                label = option.get("label")
                key = f"{room.room_code}_option_{label}"
                text = st.session_state.get(key, "").strip()
                if text:
                    option["text"] = text
            state.setdefault("multiple_choice", {})["options"] = options
            state["phase"] = "guessing"
            state["listener_guesses"] = {}
            self._save_state(room, state)

    def _render_guess_phase(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
        current_player_id: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Guessing")
        question = (state.get("question") or {}).get("question", "")
        if question:
            st.markdown(f"**Question:** {question}")
        options = state.get("multiple_choice", {}).get("options", [])
        if not options:
            st.warning("Options not ready yet.")
            return
        lookup = {opt["label"]: opt for opt in options}
        listeners = [player for player in room.players if player.player_id != storyteller_id]
        guesses = state.get("listener_guesses", {})

        option_display = [f"{opt['label']}. {opt['text']}" for opt in options]
        display_to_label = {display: opt["label"] for display, opt in zip(option_display, options)}

        option_labels = [opt["label"] for opt in options]

        def _show_option_list() -> None:
            st.markdown("**Options**")
            for option in options:
                st.write(f"{option['label']}. {option['text']}")

        # Listener view
        if current_player_id and current_player_id in {player.player_id for player in listeners}:
            if current_player_id in guesses:
                # Waiting screen after this listener has submitted
                _show_option_list()
                my_guess = guesses[current_player_id]
                chosen_label = my_guess.get("label")
                chosen_option = lookup.get(chosen_label, {})
                st.markdown("**Your choice**")
                st.write(f"{chosen_label}. {chosen_option.get('text', '')}")
                st.info("Waiting for the other players to finish their guesses...")
            else:
                # Initial guess input
                default_index = 0
                selection_display = st.radio(
                    "Options",
                    options=option_display,
                    index=default_index,
                    key=f"{room.room_code}_guess_select",
                )
                selection = display_to_label.get(selection_display, option_labels[default_index])
                if st.button("Submit my guess"):
                    guesses[current_player_id] = {
                        "label": selection,
                        "kind": lookup.get(selection, {}).get("kind"),
                    }
                    state["listener_guesses"] = guesses
                    self._save_state(room, state)
                    st.success("Guess submitted.")
        else:
            # Storyteller / host / observers
            _show_option_list()
            st.info("Waiting for listeners to submit their guesses...")

        remaining = [p.name for p in listeners if p.player_id not in guesses]
        if remaining:
            st.caption("Still waiting for: " + ", ".join(remaining))
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
        st.markdown(f"**Question:** {question}")

        options = (state.get("multiple_choice") or {}).get("options", [])
        if options:
            st.markdown("**Options**")
            for opt in options:
                label = opt.get("label")
                text = opt.get("text", "")
                kind = opt.get("kind")
                line = f"{label}. {text}"
                if kind == "true":
                    st.markdown(
                        f"<span style='color:green; font-weight:bold'>{line}</span>",
                        unsafe_allow_html=True,
                    )
                elif kind == "trap":
                    st.markdown(
                        f"<span style='color:red; font-weight:bold'>{line}</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.write(line)

        if not state.get("round_summary"):
            summary = self._compute_scoring(room, state, storyteller_id)
            state["round_summary"] = summary
            self._save_state(room, state)
        else:
            summary = state["round_summary"]

        guesses = summary.get("guesses", {})
        lookup = self._player_lookup(room)
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
    def _current_theme(self, room: Room, state: Dict[str, object]) -> str:
        theme = state.get("selected_theme")
        if not theme and room.settings.theme_mode == ThemeMode.STATIC and room.settings.selected_themes:
            theme = room.settings.selected_themes[0]
        return theme or "Open conversation"

    def _current_level_value(self, room: Room, state: Dict[str, object]) -> str:
        level_value = state.get("selected_level")
        if not level_value and room.settings.level_mode == LevelMode.STATIC and room.settings.selected_level:
            level_value = room.settings.selected_level.value
        return level_value or Level.SHALLOW.value

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
        try:
            prev = state.get("question_history", [])[-5:]
            with st.spinner("Preparing a fresh question..."):
                resp = self.llm_service.generate_question(
                    theme=state.get("selected_theme") or "General",
                    level=Level(state.get("selected_level", Level.SHALLOW.value)),
                    previous_questions=prev,
                    language=room.settings.language,
                )
        except Exception as exc:
            self.game_service.set_state(room, state)
            st.error(f"Content service error: {exc}")
            return False
        payload = resp.model_dump()
        state["question"] = payload
        state.setdefault("question_history", []).append(payload["question"])
        st.session_state[prefill_key] = payload["question"]
        if notify:
            st.success("Question updated.")
        self._save_state(room, state)
        return True

    def _prepare_options(
        self,
        room: Room,
        state: Dict[str, object],
        *,
        force: bool = False,
    ) -> bool:
        if not state.get("true_answer"):
            return False
        if not force and state.get("options_autogen_attempted"):
            return False
        state["options_autogen_attempted"] = True
        try:
            with st.spinner("Preparing multiple choices..."):
                resp = self.llm_service.build_multiple_choice(
                    question=state.get("question", {}).get("question", ""),
                    true_answer=state.get("true_answer", ""),
                    level=Level(state.get("selected_level", Level.SHALLOW.value)),
                    trap_answer=state.get("trap_answer"),
                    language=room.settings.language,
                )
        except Exception as exc:
            self.game_service.set_state(room, state)
            st.error(f"Content service error: {exc}")
            return False
        payload = resp.model_dump()
        payload["options"] = self._shuffle_options(payload.get("options", []))
        state["multiple_choice"] = payload
        if force:
            st.success("Options updated.")
        self._save_state(room, state)
        return True

    def _save_state(self, room: Room, state: Dict[str, object]) -> None:
        self.game_service.set_state(room, state)
        common.rerun()

    def _compute_scoring(
        self,
        room: Room,
        state: Dict[str, object],
        storyteller_id: Optional[str],
    ) -> Dict[str, object]:
        options = {opt["label"]: opt for opt in state.get("multiple_choice", {}).get("options", [])}
        guesses = state.get("listener_guesses", {})
        multiplier = {"shallow": 1, "medium": 2, "deep": 3}.get(state.get("selected_level", Level.SHALLOW.value), 1)
        listeners = [player for player in room.players if player.player_id != storyteller_id]
        correct = [pid for pid, guess in guesses.items() if options.get(guess["label"], {}).get("kind") == "true"]
        trap = [pid for pid, guess in guesses.items() if options.get(guess["label"], {}).get("kind") == "trap"]
        deltas = {pid: 0 for pid in state.get("scores", {})}

        if room.settings.gameplay_mode == GameplayMode.SIMPLE:
            for pid in correct:
                deltas[pid] += 1 * multiplier
            if not listeners:
                storyteller_points = 0
            elif len(correct) == len(listeners) and listeners:
                storyteller_points = 2 * multiplier
            elif correct:
                storyteller_points = 1 * multiplier
            else:
                storyteller_points = 0
            if storyteller_id:
                deltas[storyteller_id] += storyteller_points
        else:
            if len(correct) == 1:
                for pid in correct:
                    deltas[pid] += 3 * multiplier
                if storyteller_id:
                    deltas[storyteller_id] += 3 * multiplier
            elif len(correct) == len(listeners) and listeners:
                for pid in correct:
                    deltas[pid] += 2 * multiplier
            else:
                for pid in correct:
                    deltas[pid] += 1 * multiplier
                if correct and len(correct) < len(listeners):
                    if storyteller_id:
                        deltas[storyteller_id] += 1 * multiplier

        # update global scores
        for pid, delta in deltas.items():
            state["scores"][pid] = state["scores"].get(pid, 0) + delta

        winners = [pid for pid, score in state["scores"].items() if score >= room.settings.max_score]
        return {
            "guesses": guesses,
            "deltas": deltas,
            "correct": correct,
            "trap": trap,
            "winners": winners,
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
