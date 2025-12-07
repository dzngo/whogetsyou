"""Streamlit-based rendering of the host pre-game journey."""

from __future__ import annotations

from typing import Dict, Optional

import streamlit as st

from models import (
    SUPPORTED_LLM_MODELS,
    GameplayMode,
    Level,
    LevelMode,
    PlayerRole,
    RoomSettings,
    ThemeMode,
    LANGUAGE_FLAGS,
    SUPPORTED_LANGUAGES,
)
from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import InvalidRoomSettingsError, RoomService
from ui import common


class HostFlow:
    STATE_KEY = "host_flow"

    def __init__(
        self,
        room_service: RoomService,
        llm_service: LLMService,
        game_service: GameService,
    ) -> None:
        self.room_service = room_service
        self.llm_service = llm_service
        self.game_service = game_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "host_name",
            "host_name": "",
            "room_name": "",
            "room_code": None,
            "existing_room_code": None,
            "editing_existing": False,
            "theme_mode": ThemeMode.DYNAMIC.value,
            "selected_themes": [],
            "custom_themes": [],
            "level_mode": LevelMode.DYNAMIC.value,
            "selected_level": Level.NARROW.value,
            "language": "en",
            "llm_model": "gemini-2.5-flash",
            "clear_custom_theme_input": False,
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        return common.get_flow_state(self.STATE_KEY, defaults=self._default_state())

    def render(self) -> None:
        step = self.state["step"]
        if step == "host_name":
            self._render_host_name()
        elif step == "room_name":
            self._render_room_name()
        elif step == "existing_room_decision":
            self._render_existing_room_decision()
        elif step == "theme_mode":
            self._render_theme_mode()
        elif step == "level_mode":
            self._render_level_mode()
        elif step == "language":
            self._render_language()
        elif step == "lobby":
            self._render_lobby()
        else:
            st.warning("Unknown step. Resetting flow.")
            self.reset()
            common.rerun()

    def _render_host_name(self) -> None:
        state = self.state
        st.subheader("Host name")
        name = st.text_input("Your name", value=state["host_name"])
        if st.button("Next", key="host_name_next"):
            cleaned = name.strip()
            if not cleaned:
                st.error("Please enter your name.")
            else:
                state["host_name"] = cleaned
                state["step"] = "room_name"
                common.rerun()

    def _render_room_name(self) -> None:
        state = self.state
        st.subheader("Room name")
        name = st.text_input("Room name", value=state["room_name"])
        col1, col2 = st.columns(2)
        if col1.button("Back", key="room_name_back"):
            state["step"] = "host_name"
            common.rerun()
        if col2.button("Next", key="room_name_next"):
            cleaned = name.strip()
            if not cleaned:
                st.error("Please enter a room name.")
                return
            state["room_name"] = cleaned
            existing = self.room_service.get_room_by_name(cleaned)
            if existing:
                state["existing_room_code"] = existing.room_code
                state["editing_existing"] = False
                state["step"] = "existing_room_decision"
            else:
                state["existing_room_code"] = None
                state["editing_existing"] = False
                state["step"] = "theme_mode"
            common.rerun()

    def _render_existing_room_decision(self) -> None:
        state = self.state
        st.subheader("Reuse existing room")
        room = self._get_existing_room()
        if not room:
            st.info("Room not found anymore. Let's create a new one.")
            state["step"] = "theme_mode"
            common.rerun()
            return
        st.success("A room with this name/code already exists.")
        common.show_room_summary(room)
        col1, col2, col3 = st.columns(3)
        if col1.button("Reuse room", key="existing_reuse"):
            updated = self.room_service.reuse_room(room, state["host_name"])
            state["room_code"] = updated.room_code
            state["step"] = "lobby"
            common.rerun()
        if col2.button("Change settings", key="existing_change"):
            state["editing_existing"] = True
            state["theme_mode"] = room.settings.theme_mode.value
            state["selected_themes"] = list(room.settings.selected_themes)
            state["custom_themes"] = []
            state["level_mode"] = room.settings.level_mode.value
            state["selected_level"] = (
                room.settings.selected_level.value if room.settings.selected_level else Level.NARROW.value
            )
            state["language"] = room.settings.language
            state["llm_model"] = room.settings.llm_model
            state["step"] = "theme_mode"
            common.rerun()
        if col3.button("Back", key="existing_back"):
            state["step"] = "room_name"
            common.rerun()

    def _render_theme_mode(self) -> None:
        state = self.state
        if state.get("clear_custom_theme_input"):
            state["clear_custom_theme_input"] = False
            st.session_state["custom_theme_input"] = ""
        st.subheader("Select theme mode")
        mode = st.radio(
            "Theme mode",
            options=[ThemeMode.STATIC.value, ThemeMode.DYNAMIC.value],
            format_func=lambda value: value.title(),
            index=0 if state["theme_mode"] == ThemeMode.STATIC.value else 1,
            key="theme_mode_radio",
        )
        state["theme_mode"] = mode
        selected_themes = list(state["selected_themes"])
        if mode == ThemeMode.STATIC.value:
            st.caption("Choose at least one theme.")
            suggestions = self.llm_service.suggest_themes()
            available = list(dict.fromkeys(suggestions + state["custom_themes"]))
            selected = st.multiselect(
                "Suggested themes",
                options=available,
                default=[theme for theme in selected_themes if theme in available],
            )
            custom_input = st.text_input(
                "Add custom theme(s) separated by comma",
                key="custom_theme_input",
            )
            if st.button("Add custom themes", key="add_custom_themes"):
                new_entries = [item.strip().title() for item in custom_input.split(",") if item.strip()]
                new_custom = list(state["custom_themes"])
                changed = False
                for entry in new_entries:
                    if entry not in new_custom:
                        new_custom.append(entry)
                        changed = True
                rerun_needed = False
                if changed:
                    state["custom_themes"] = new_custom
                    rerun_needed = True
                if new_entries:
                    state["clear_custom_theme_input"] = True
                    rerun_needed = True
                if rerun_needed:
                    common.rerun()
            state["selected_themes"] = selected
        else:
            state["selected_themes"] = []
            state["custom_themes"] = []

        back_target = (
            "existing_room_decision" if state["editing_existing"] and state["existing_room_code"] else "room_name"
        )
        col1, col2 = st.columns(2)
        if col1.button("Back", key="theme_back"):
            state["step"] = back_target
            common.rerun()
        if col2.button("Next", key="theme_next"):
            if mode == ThemeMode.STATIC.value:
                final_themes = state["selected_themes"] + [
                    theme for theme in state["custom_themes"] if theme not in state["selected_themes"]
                ]
                if not final_themes:
                    st.error("Select at least one theme for static mode.")
                    return
                state["selected_themes"] = final_themes
            state["step"] = "level_mode"
            common.rerun()

    def _render_level_mode(self) -> None:
        state = self.state
        st.subheader("Select level mode")
        mode = st.radio(
            "Level mode",
            options=[LevelMode.STATIC.value, LevelMode.DYNAMIC.value],
            format_func=lambda value: value.title(),
            index=0 if state["level_mode"] == LevelMode.STATIC.value else 1,
            key="level_mode_radio",
        )
        state["level_mode"] = mode
        level_choice: Optional[str] = None
        if mode == LevelMode.STATIC.value:
            level_choice = st.selectbox(
                "Choose level",
                options=[Level.NARROW.value, Level.MEDIUM.value, Level.DEEP.value],
                format_func=lambda value: value.title(),
                index=[
                    Level.NARROW.value,
                    Level.MEDIUM.value,
                    Level.DEEP.value,
                ].index(state["selected_level"]),
            )
            state["selected_level"] = level_choice
        else:
            state["selected_level"] = Level.NARROW.value

        col1, col2 = st.columns(2)
        if col1.button("Back", key="level_back"):
            state["step"] = "theme_mode"
            common.rerun()
        if col2.button("Next", key="level_next"):
            state["step"] = "language"
            common.rerun()

    def _render_language(self) -> None:
        state = self.state
        st.subheader("Select language")
        language_codes = list(SUPPORTED_LANGUAGES.keys())
        current_language = state.get("language", "en")
        try:
            language_index = language_codes.index(current_language)
        except ValueError:
            language_index = 0

        def _format_language(code: str) -> str:
            flag = LANGUAGE_FLAGS.get(code, "")
            name = SUPPORTED_LANGUAGES.get(code, code.upper())
            return f"{flag} {name}".strip()

        selected_language = st.selectbox(
            "Language",
            options=language_codes,
            index=language_index,
            format_func=_format_language,
        )
        state["language"] = selected_language

        llm_codes = list(SUPPORTED_LLM_MODELS.keys())
        current_llm = state.get("llm_model", "gemini-2.5-flash")
        try:
            llm_index = llm_codes.index(current_llm)
        except ValueError:
            llm_index = 0
        selected_llm = st.selectbox(
            "LLM provider",
            options=llm_codes,
            index=llm_index,
            format_func=lambda code: SUPPORTED_LLM_MODELS.get(code, code),
        )
        state["llm_model"] = selected_llm

        col1, col2 = st.columns(2)
        if col1.button("Back", key="language_back"):
            state["step"] = "level_mode"
            common.rerun()
        if col2.button("Next", key="language_next"):
            settings = self._build_room_settings(state)
            try:
                if state["editing_existing"] and state["existing_room_code"]:
                    room = self._get_existing_room()
                    if not room:
                        st.error("Room no longer exists. Please start over.")
                        state["step"] = "room_name"
                        common.rerun()
                        return
                    updated = self.room_service.reconfigure_room(room, state["host_name"], settings)
                    state["room_code"] = updated.room_code
                else:
                    room = self.room_service.create_room(state["host_name"], state["room_name"], settings)
                    state["room_code"] = room.room_code
            except InvalidRoomSettingsError as exc:
                st.error(str(exc))
                return
            state["step"] = "lobby"
            state["editing_existing"] = False
            common.rerun()

    def _render_lobby(self) -> None:
        state = self.state
        st.subheader("Room lobby (Host)")
        room = self._load_room(state["room_code"])
        if not room:
            st.warning("Room could not be found. Let's start again.")
            self.reset()
            common.rerun()
            return
        st.session_state["player_profile"] = {
            "player_id": room.host_id,
            "room_code": room.room_code,
            "name": room.host_name,
        }
        common.show_room_summary(room)
        st.markdown("### Connected players")
        for player in room.players:
            suffix = " (Host)" if player.role.value == "host" else ""
            st.write(f"- {player.name}{suffix}")

        with st.form("gameplay_mode_form"):
            selected_mode = st.radio(
                "Gameplay mode",
                options=[GameplayMode.SIMPLE.value, GameplayMode.BLUFFING.value],
                format_func=lambda value: value.title(),
                index=0 if room.settings.gameplay_mode == GameplayMode.SIMPLE else 1,
            )
            submitted = st.form_submit_button("Update gameplay mode")
        if submitted and selected_mode != room.settings.gameplay_mode.value:
            self.room_service.adjust_gameplay_mode(room, GameplayMode(selected_mode))
            common.rerun()

        with st.form("max_score_form"):
            score = st.number_input(
                "Max score",
                min_value=1,
                value=int(room.settings.max_score),
            )
            score_submit = st.form_submit_button("Update max score")
        if score_submit and score != room.settings.max_score:
            self.room_service.update_max_score(room, int(score))
            common.rerun()

        removable_players = [player for player in room.players if player.role != PlayerRole.HOST]
        if removable_players:
            with st.form("remove_player_form"):
                choices = {player.player_id: player for player in removable_players}
                selected_id = st.selectbox(
                    "Remove a player",
                    options=list(choices.keys()),
                    format_func=lambda pid: choices[pid].name,
                    index=0,
                )
                remove_submit = st.form_submit_button("Remove player")
            if remove_submit and selected_id:
                self.room_service.remove_player(room, selected_id)
                st.success("Player removed from the room.")
                common.rerun()
        else:
            st.caption("No players to remove.")

        st.markdown("### Game controls")
        can_start = len(room.players) >= 2
        if not can_start:
            st.warning("At least two players are required to start the game.")
        else:
            if st.button("Start game"):
                try:
                    self.game_service.start_game(room)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["active_room_code"] = room.room_code
                    st.session_state["route"] = "game"
                    common.rerun()

        col1, col2 = st.columns(2)
        if col1.button("Refresh lobby", key="lobby_refresh"):
            common.rerun()
        if col2.button("Change room", key="lobby_change_room"):
            state["step"] = "room_name"
            state["existing_room_code"] = None
            state["room_code"] = None
            st.session_state.pop("active_room_code", None)
            common.rerun()

    def _build_room_settings(self, state: Dict[str, object]) -> RoomSettings:
        theme_mode = ThemeMode(state["theme_mode"])
        level_mode = LevelMode(state["level_mode"])
        selected_themes = state["selected_themes"] if theme_mode == ThemeMode.STATIC else []
        full_theme_list = list(selected_themes)
        if theme_mode == ThemeMode.STATIC:
            custom = [theme for theme in state["custom_themes"] if theme not in full_theme_list]
            full_theme_list.extend(custom)
        selected_level = Level(state["selected_level"]) if level_mode == LevelMode.STATIC else None
        existing_room = self._get_existing_room() if state["editing_existing"] else None
        gameplay_mode = existing_room.settings.gameplay_mode if existing_room else GameplayMode.SIMPLE
        max_score = existing_room.settings.max_score if existing_room else 100
        return RoomSettings(
            theme_mode=theme_mode,
            selected_themes=full_theme_list if theme_mode == ThemeMode.STATIC else [],
            level_mode=level_mode,
            selected_level=selected_level,
            gameplay_mode=gameplay_mode,
            max_score=max_score,
            language=state.get("language", "en"),
            llm_model=state.get("llm_model", "gemini-2.5-flash"),
        )

    def _get_existing_room(self):
        code = self.state.get("existing_room_code")
        if not code:
            return None
        return self._load_room(code)

    def _load_room(self, room_code):
        if not room_code:
            return None
        return self.room_service.get_room_by_code(room_code)
