"""Streamlit implementation of the in-game flow."""

from __future__ import annotations

import copy
import random
from typing import Dict, List, Optional

import streamlit as st

from models import (
    DEFAULT_THEMES,
    LANGUAGE_FLAGS,
    SUPPORTED_LANGUAGES,
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
            st.info("Waiting for the host to start the game.")
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
        listeners = [p for p in room.players if p.player_id != storyteller_id]

        self._render_board(
            room,
            state,
            storyteller,
            listeners,
            current_player_id,
            current_player_name,
            is_host,
        )

        phase = state.get("phase")
        if phase == "theme_selection":
            self._render_theme_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "level_selection":
            self._render_level_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "question_generation":
            self._render_question_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "answer_entry":
            self._render_answer_phase(room, state, storyteller_id, current_player_id, is_host)
        elif phase == "options":
            self._render_options_phase(room, state, storyteller_id, current_player_id, is_host)
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
        listeners: List[Player],
        current_player_id: Optional[str],
        current_player_name: Optional[str],
        is_host: bool,
    ) -> None:
        st.subheader("Game board")
        columns = st.columns(2)
        with columns[0]:
            st.write(f"**Room**: {room.name}")
            st.write(f"**Gameplay mode**: {room.settings.gameplay_mode.value.title()}")
            theme_desc = (
                f"Static ({', '.join(room.settings.selected_themes)})"
                if room.settings.theme_mode == ThemeMode.STATIC and room.settings.selected_themes
                else room.settings.theme_mode.value.title()
            )
            st.write(f"**Theme mode**: {theme_desc}")
        with columns[1]:
            level_desc = (
                f"Static ({room.settings.selected_level.value.title()})"
                if room.settings.level_mode == LevelMode.STATIC and room.settings.selected_level
                else room.settings.level_mode.value.title()
            )
            st.write(f"**Level mode**: {level_desc}")
            st.write(f"**Target score**: {room.settings.max_score}")
            language_name = SUPPORTED_LANGUAGES.get(room.settings.language.lower(), room.settings.language.upper())
            flag = LANGUAGE_FLAGS.get(room.settings.language.lower(), "")
            language_display = f"{flag} {language_name}".strip()
            st.write(f"**Language**: {language_display}")

        st.markdown("### Scoreboard")
        lookup = self._player_lookup(room)
        scoreboard = sorted((pid, score) for pid, score in (state.get("scores") or {}).items())
        scoreboard.sort(key=lambda item: item[1], reverse=True)
        for pid, score in scoreboard:
            player = lookup.get(pid)
            if not player:
                continue
            marker = "💬" if pid == self._current_storyteller_id(state) else ""
            st.write(f"- {player.name}: **{score}** {marker}")

        if current_player_name:
            st.caption(f"You are playing as **{current_player_name}**")

        current_theme = state.get("selected_theme") or (
            "To be selected" if room.settings.theme_mode == ThemeMode.DYNAMIC else "Static rotation"
        )
        current_level = state.get("selected_level") or (
            "To be selected" if room.settings.level_mode == LevelMode.DYNAMIC else "Static"
        )
        st.write(f"**Current theme:** {current_theme}")
        st.write(f"**Current level:** {current_level.title() if isinstance(current_level, str) else current_level}")

        storyteller_name = storyteller.name if storyteller else "Unknown"
        phase_labels = {
            "theme_selection": "Waiting for the storyteller to choose a theme.",
            "level_selection": "Waiting for the storyteller to set the depth.",
            "question_generation": "Storyteller is validating the question.",
            "answer_entry": "Storyteller is entering their answers.",
            "options": "Storyteller is preparing multiple choice options.",
            "guessing": "Listeners are guessing the answer.",
            "reveal": "Revealing the round outcome.",
            "results": "Final results.",
        }
        st.info(
            f"**Round {state.get('round', 1)}** – Current Storyteller: {storyteller_name}  \n"
            f"{phase_labels.get(state.get('phase'), '')}"
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
        is_host: bool,
    ) -> None:
        st.subheader("Phase 1 – Choose theme")
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

        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            st.info("Waiting for the Storyteller to pick a theme.")
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
        is_host: bool,
    ) -> None:
        st.subheader("Phase 1 – Choose level")
        if room.settings.level_mode == LevelMode.STATIC:
            level = room.settings.selected_level.value if room.settings.selected_level else Level.NARROW.value
            st.info(f"Static level confirmed: **{level.title()}**")
            state["selected_level"] = level
            state["phase"] = "question_generation"
            self._save_state(room, state)
            return

        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if not can_act:
            st.info("Waiting for the Storyteller to pick the depth.")
            return

        level = st.selectbox(
            "Question depth",
            options=[Level.NARROW.value, Level.MEDIUM.value, Level.DEEP.value],
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
        is_host: bool,
    ) -> None:
        st.subheader("Phase 2 – Question proposal")
        question_data = state.get("question") or {}
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        if question_data:
            st.markdown(f"**Current question:** {question_data.get('question')}")
            if reason := question_data.get("reason"):
                st.caption(reason)

        if not can_act:
            st.info("Waiting for the Storyteller to validate a question.")
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
        if st.button("Change question"):
            if self._prepare_question(room, state, prefill_key, notify=True, force=True):
                return

        if st.button("Confirm question"):
            final_question = manual_value.strip()
            if not final_question:
                st.error("Please enter a question.")
                return
            state["question"] = {
                "question": final_question,
                "reason": question_data.get("reason", "Provided manually."),
            }
            state.setdefault("question_history", []).append(final_question)
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
        st.subheader("Phase 3 – Storyteller answers")
        question = (state.get("question") or {}).get("question")
        if not question:
            st.warning("Question not set yet.")
            return
        st.markdown(f"**Question:** {question}")

        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
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
        st.text_area(
            "True answer",
            key=true_key,
            disabled=not can_act,
        )
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

        if not can_act:
            st.info("Waiting for the Storyteller to confirm their answers.")
            return

        col1, col2 = st.columns(2)
        storyteller_name = storyteller_obj.name if storyteller_obj else "Storyteller"
        if col1.button("Suggest honest answer"):
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
        if room.settings.gameplay_mode == GameplayMode.BLUFFING and col2.button("Suggest trap answer"):
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
        is_host: bool,
    ) -> None:
        st.subheader("Phase 4 – Build multiple choice options")
        question = (state.get("question") or {}).get("question", "")
        if question:
            st.markdown(f"**Question:** {question}")
        can_act = self._storyteller_can_act(storyteller_id, current_player_id)
        multiple_choice = state.get("multiple_choice") or {}
        options = multiple_choice.get("options", [])

        if not can_act:
            st.info("Waiting for the Storyteller to confirm the options.")
            return

        if not options and state.get("true_answer"):
            if self._prepare_options(room, state):
                return

        if options:
            st.markdown("**Current options:**")
            for option in options:
                label = option.get("label")
                text = option.get("text")
                kind = option.get("kind")
                st.write(f"{label}. {text} ({kind})")

        if st.button("Change options"):
            if self._prepare_options(room, state, force=True):
                return

        if options and st.button("Confirm options & invite guesses"):
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
        st.subheader("Phase 5 – Guessing")
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

        st.markdown("**Options**")
        for option in options:
            st.write(f"{option['label']}. {option['text']}")

        option_labels = [opt["label"] for opt in options]
        if current_player_id and current_player_id in {player.player_id for player in listeners}:
            current_guess = guesses.get(current_player_id, {}).get("label")
            default_index = 0
            if current_guess in option_labels:
                default_index = option_labels.index(current_guess)
            selection = st.selectbox(
                "Your guess",
                options=option_labels,
                index=default_index,
                key=f"{room.room_code}_guess_select",
            )
            if st.button("Submit my guess"):
                guesses[current_player_id] = {
                    "label": selection,
                    "kind": lookup.get(selection, {}).get("kind"),
                }
                state["listener_guesses"] = guesses
                self._save_state(room, state)
                st.success("Guess submitted.")
        else:
            st.info("Waiting for listeners to submit their guesses.")

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
        st.subheader("Phase 6 – Reveal & scoring")
        question = (state.get("question") or {}).get("question", "")
        st.markdown(f"**Question:** {question}")
        st.write(f"**True answer:** {state.get('true_answer')}")
        if state.get("trap_answer"):
            st.write(f"**Trap answer:** {state.get('trap_answer')}")

        if not state.get("round_summary"):
            summary = self._compute_scoring(room, state, storyteller_id)
            state["round_summary"] = summary
            self._save_state(room, state)
        else:
            summary = state["round_summary"]

        guesses = summary.get("guesses", {})
        lookup = self._player_lookup(room)
        st.markdown("**Listener guesses**")
        for player_id, guess in guesses.items():
            player = lookup.get(player_id)
            if not player:
                continue
            label = guess.get("label")
            kind = guess.get("kind")
            st.write(f"- {player.name}: option {label} ({kind})")

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
            self._save_state(room, state)
            return

        if (current_player_id == storyteller_id) or is_host:
            if st.button("Next turn"):
                self.game_service.prepare_next_turn(room, advance_round=True)
                common.rerun()

    def _render_results(self, room: Room, state: Dict[str, object], is_host: bool) -> None:
        st.subheader("Final results")
        lookup = self._player_lookup(room)
        winners = state.get("winners", [])
        if winners:
            names = ", ".join(lookup[pid].name for pid in winners if pid in lookup)
            st.success(f"Winner(s): {names}")
        scoreboard = sorted((pid, score) for pid, score in (state.get("scores") or {}).items())
        scoreboard.sort(key=lambda item: item[1], reverse=True)
        st.markdown("### Final scoreboard")
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
                    level=Level(state.get("selected_level", Level.NARROW.value)),
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
            with st.spinner("Preparing answer options..."):
                resp = self.llm_service.build_multiple_choice(
                    question=state.get("question", {}).get("question", ""),
                    true_answer=state.get("true_answer", ""),
                    gameplay_mode=room.settings.gameplay_mode,
                    level=Level(state.get("selected_level", Level.NARROW.value)),
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
        multiplier = {"narrow": 1, "medium": 2, "deep": 3}.get(state.get("selected_level", Level.NARROW.value), 1)
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
            st.success("Game ended by host.")
        self._save_state(room, state)

    def _shuffle_options(self, options: List[Dict[str, object]]) -> List[Dict[str, object]]:
        shuffled = [dict(option) for option in options]
        random.shuffle(shuffled)
        for idx, option in enumerate(shuffled):
            option["label"] = chr(ord("A") + idx)
        return shuffled
