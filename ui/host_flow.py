"""Streamlit-based rendering of the host pre-game journey."""

from __future__ import annotations

from typing import Dict

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from models import (
    SUPPORTED_LLM_MODELS,
    LANGUAGE_FLAGS,
    SUPPORTED_LANGUAGES,
    PlayerRole,
    RoomSettings,
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
            "language": "en",
            "llm_model": "gemini-2.5-flash",
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        state = common.get_flow_state(self.STATE_KEY, defaults=self._default_state())
        defaults = self._default_state()
        for key, value in defaults.items():
            state.setdefault(key, value)
        return state

    def render(self) -> None:
        step = self.state["step"]
        if step == "host_name":
            self._render_host_name()
        elif step == "room_name":
            self._render_room_name()
        elif step == "existing_room_decision":
            self._render_existing_room_decision()
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
        st.subheader("Your name")
        host_name = st.text_input("Host name", value=state["host_name"])
        col1, col2 = st.columns(2)
        if col1.button("Back", key="host_name_back"):
            self.reset()
            st.session_state["route"] = "entry"
            common.rerun()
        if col2.button("Next", key="host_name_next"):
            cleaned = host_name.strip()
            if not cleaned:
                st.error("Please enter your name.")
                return
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
                state["step"] = "language"
            common.rerun()

    def _render_existing_room_decision(self) -> None:
        state = self.state
        st.subheader("Reuse existing room")
        room = self._get_existing_room()
        if not room:
            st.info("Room not found anymore. Let's create a new one.")
            state["step"] = "language"
            common.rerun()
            return
        st.success("A room with this name already exists.")
        common.show_room_summary(room)
        col1, col2, col3 = st.columns(3)
        if col1.button("Reuse room", key="existing_reuse"):
            updated = self.room_service.reuse_room(room, state["host_name"])
            state["room_code"] = updated.room_code
            state["step"] = "lobby"
            common.rerun()
        if col2.button("Change settings", key="existing_change"):
            state["editing_existing"] = True
            state["language"] = room.settings.language
            state["llm_model"] = room.settings.llm_model
            state["step"] = "language"
            common.rerun()
        if col3.button("Back", key="existing_back"):
            state["step"] = "room_name"
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
            back_target = "existing_room_decision" if state.get("existing_room_code") else "room_name"
            state["step"] = back_target
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
                    updated = self.room_service.reconfigure_room(
                        room,
                        state["host_name"],
                        settings,
                    )
                    state["room_code"] = updated.room_code
                else:
                    room = self.room_service.create_room(
                        state["host_name"],
                        state["room_name"],
                        settings,
                    )
                    state["room_code"] = room.room_code
            except InvalidRoomSettingsError as exc:
                st.error(str(exc))
                return
            state["step"] = "lobby"
            state["editing_existing"] = False
            common.rerun()

    def _render_lobby(self) -> None:
        state = self.state
        room = self._load_room(state["room_code"])
        if not room:
            st.warning("Room could not be found. Let's start again.")
            self.reset()
            common.rerun()
            return

        st_autorefresh(interval=1000, key=f"host_lobby_autorefresh_{room.room_code}")

        st.session_state["player_profile"] = {
            "player_id": room.host_id,
            "room_code": room.room_code,
            "name": room.host_name,
        }
        common.show_room_summary(room, display_llm=True)
        st.markdown("### Connected players")
        with st.container(border=True):
            for player in room.players:
                suffix = " (Host)" if player.role == PlayerRole.HOST else ""
                st.write(f"- {player.name}{suffix}")

        st.markdown("### Game settings")
        with st.container(border=True):
            score = st.number_input(
                "Max score",
                min_value=1,
                value=int(room.settings.max_score),
                key="host_lobby_max_score",
            )

            if int(score) != room.settings.max_score:
                self.room_service.update_max_score(room, int(score))
                common.rerun()
                return

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

        can_start = len(room.players) >= 3
        if not can_start:
            st.warning("At least three players are required to start the game.")
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
        existing_room = self._get_existing_room() if state["editing_existing"] else None
        max_score = existing_room.settings.max_score if existing_room else 100
        return RoomSettings(
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
