"""Streamlit implementation of the joiner flow."""

from __future__ import annotations

from typing import Dict

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from services.room_service import PlayerNotFoundError, RoomAlreadyStartedError, RoomService
from ui import common


class JoinFlow:
    STATE_KEY = "join_flow"

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "room_code",
            "player_name": "",
            "player_id": None,
            "room_code_input": "",
            "candidate_room_code": None,
            "joined_room_code": None,
            "selected_player_id": None,
        }

    def reset(self) -> None:
        common.reset_flow_state(self.STATE_KEY, defaults=self._default_state())

    @property
    def state(self) -> Dict[str, object]:
        return common.get_flow_state(self.STATE_KEY, defaults=self._default_state())

    def render(self) -> None:
        step = self.state["step"]
        if step == "room_code":
            self._render_room_code()
        elif step == "player_name":
            self._render_player_name()
        elif step == "reclaim_player":
            self._render_reclaim_player()
        elif step == "lobby":
            self._render_lobby()
        else:
            st.warning("Unknown step. Resetting join flow.")
            self.reset()
            common.rerun()

    def _render_room_code(self) -> None:
        state = self.state
        st.subheader("Enter room code")
        room_code = st.text_input("Room code", value=state["room_code_input"])
        col1, col2 = st.columns(2)
        if col1.button("Back", key="room_code_back"):
            self.reset()
            st.session_state["route"] = "entry"
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
                state["candidate_room_code"] = cleaned
                state["selected_player_id"] = None
                state["step"] = "reclaim_player"
                common.rerun()
                return
            state["candidate_room_code"] = cleaned
            state["step"] = "player_name"
            common.rerun()

    def _render_player_name(self) -> None:
        state = self.state
        room_code = state.get("candidate_room_code")
        room = self.room_service.get_room_by_code(room_code) if room_code else None
        if not room:
            st.warning("Room was closed or no longer exists.")
            state["step"] = "room_code"
            state["candidate_room_code"] = None
            common.rerun()
            return
        if room.started:
            state["step"] = "reclaim_player"
            common.rerun()
            return

        st.subheader("Your name")
        player_name = st.text_input("Player name", value=state["player_name"])
        col1, col2 = st.columns(2)
        if col1.button("Back", key="player_name_back"):
            state["step"] = "room_code"
            common.rerun()
        if col2.button("Join room", key="player_name_join"):
            cleaned_name = player_name.strip()
            if not cleaned_name:
                st.error("Please enter your name.")
                return
            state["player_name"] = cleaned_name
            try:
                player = self.room_service.add_player(room, cleaned_name)
            except RoomAlreadyStartedError:
                state["step"] = "reclaim_player"
                common.rerun()
                return
            state["player_id"] = player.player_id
            state["joined_room_code"] = room.room_code
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
            }
            if player.player_id == room.host_id:
                self._resume_host_lobby(room.room_code, player.name)
                return
            state["step"] = "lobby"
            common.rerun()

    def _render_reclaim_player(self) -> None:
        state = self.state
        room_code = state.get("candidate_room_code")
        room = self.room_service.get_room_by_code(room_code) if room_code else None
        if not room:
            st.warning("Room was closed or no longer exists.")
            state["step"] = "room_code"
            state["candidate_room_code"] = None
            common.rerun()
            return
        if not room.started:
            state["step"] = "player_name"
            common.rerun()
            return
        if not room.players:
            st.warning("No players found in this room.")
            if st.button("Back", key="reclaim_empty_back"):
                state["step"] = "room_code"
                common.rerun()
            return

        st.subheader("Resume player")
        players = {player.player_id: player for player in room.players}
        options = list(players.keys())
        selected_player_id = st.selectbox(
            "Choose your player",
            options=options,
            index=0,
            format_func=lambda pid: players[pid].name,
        )
        state["selected_player_id"] = selected_player_id

        col1, col2 = st.columns(2)
        if col1.button("Back", key="reclaim_back"):
            state["step"] = "room_code"
            state["selected_player_id"] = None
            common.rerun()
        if col2.button("Resume game", key="reclaim_confirm"):
            try:
                player = self.room_service.reclaim_player(room, selected_player_id)
            except PlayerNotFoundError as exc:
                st.error(str(exc))
                return
            state["player_id"] = player.player_id
            state["player_name"] = player.name
            state["joined_room_code"] = room.room_code
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
            }
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
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
        common.show_room_summary(room, display_llm=False)
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
            state["candidate_room_code"] = None
            common.rerun()

    def _load_joined_room(self):
        code = self.state.get("joined_room_code")
        if not code:
            return None
        return self.room_service.get_room_by_code(code)

    def _resume_host_lobby(self, room_code: str, host_name: str) -> None:
        current_host_state = st.session_state.get("host_flow")
        if not isinstance(current_host_state, dict):
            current_host_state = {}
        current_host_state.setdefault("room_name", "")
        current_host_state.setdefault("existing_room_code", None)
        current_host_state.setdefault("editing_existing", False)
        current_host_state.setdefault("language", "en")
        current_host_state.setdefault("llm_model", "gemini-2.5-flash")
        current_host_state["step"] = "lobby"
        current_host_state["host_name"] = host_name
        current_host_state["room_code"] = room_code
        st.session_state["host_flow"] = current_host_state
        st.session_state["route"] = "host"
        common.rerun()

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
