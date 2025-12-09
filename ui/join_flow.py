"""Streamlit implementation of the joiner flow."""

from __future__ import annotations

from typing import Dict

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from services.room_service import RoomAlreadyStartedError, RoomService
from ui import common


class JoinFlow:
    STATE_KEY = "join_flow"

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "player_name",
            "player_name": "",
            "player_id": None,
            "room_code_input": "",
            "joined_room_code": None,
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        return common.get_flow_state(self.STATE_KEY, defaults=self._default_state())

    def render(self) -> None:
        step = self.state["step"]
        if step == "player_name":
            self._render_player_name()
        elif step == "room_code":
            self._render_room_code()
        elif step == "lobby":
            self._render_lobby()
        else:
            st.warning("Unknown step. Resetting join flow.")
            self.reset()
            common.rerun()

    def _render_player_name(self) -> None:
        state = self.state
        st.subheader("Player name")
        name = st.text_input("Your name", value=state["player_name"])
        if st.button("Next", key="join_name_next"):
            cleaned = name.strip()
            if not cleaned:
                st.error("Please enter your name.")
            else:
                state["player_name"] = cleaned
                state["step"] = "room_code"
                common.rerun()

    def _render_room_code(self) -> None:
        state = self.state
        st.subheader("Enter room code")
        room_code = st.text_input("Room code", value=state["room_code_input"])
        col1, col2 = st.columns(2)
        if col1.button("Back", key="room_code_back"):
            state["step"] = "player_name"
            common.rerun()
        if col2.button("Join room", key="room_code_next"):
            cleaned = room_code.strip().upper()
            if not cleaned:
                st.error("Please enter a room code.")
                return
            state["room_code_input"] = cleaned
            room = self.room_service.get_room_by_code(cleaned)
            if not room:
                st.error("Couldn't find any room with that code.")
                return
            if room.started:
                self._game_already_started()
                return
            try:
                player = self.room_service.add_player(room, state["player_name"])
            except RoomAlreadyStartedError:
                self._game_already_started()
                return
            state["player_id"] = player.player_id
            state["joined_room_code"] = room.room_code
            state["step"] = "lobby"
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
            }
            common.rerun()

    def _render_lobby(self) -> None:
        state = self.state
        room = self._load_joined_room()
        if not room:
            st.warning("Room was closed by the host.")
            state["step"] = "room_code"
            state["joined_room_code"] = None
            state["player_id"] = None
            common.rerun()
            return
        if room.started:
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
            common.rerun()
            return
        # Auto-refresh while waiting for the host to start the game.
        st_autorefresh(interval=1000, key=f"join_lobby_autorefresh_{room.room_code}")
        common.show_room_summary(room)
        st.markdown("### Connected players")
        with st.container(border=True):
            for player in room.players:
                you = " (You)" if player.player_id == state["player_id"] else ""
                st.write(f"- {player.name}{you}")
        st.info("Waiting for host to start the game…")
        col1, col2 = st.columns(2)
        if col1.button("Refresh", key="join_lobby_refresh"):
            common.rerun()
        if col2.button("Change room", key="join_lobby_change"):
            self._leave_current_room()
            state["step"] = "room_code"
            state["room_code_input"] = ""
            common.rerun()

    def _game_already_started(self) -> None:
        st.warning("The game in this room has already started. Please choose another room.")

    def _load_joined_room(self):
        code = self.state.get("joined_room_code")
        if not code:
            return None
        return self.room_service.get_room_by_code(code)

    def _leave_current_room(self) -> None:
        room_code = self.state.get("joined_room_code")
        player_id = self.state.get("player_id")
        if not (room_code and player_id):
            return
        room = self.room_service.get_room_by_code(room_code)
        if room:
            self.room_service.remove_player(room, player_id)
        self.state["joined_room_code"] = None
        self.state["player_id"] = None
        st.session_state.pop("player_profile", None)
        if st.session_state.get("active_room_code") == room_code:
            st.session_state.pop("active_room_code", None)
