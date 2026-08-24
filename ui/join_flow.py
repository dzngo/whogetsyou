"""Streamlit implementation of the joiner flow."""

from __future__ import annotations

from typing import Dict

import streamlit as st

from services.room_service import PlayerNotFoundError, RoomAlreadyStartedError, RoomService
from ui import common


class JoinFlow:
    STATE_KEY = "join_flow"
    REFRESH_INTERVAL_SECONDS = 3

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    @staticmethod
    def _default_state() -> Dict[str, object]:
        return {
            "step": "room_list",
            "player_name": "",
            "player_id": None,
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
        if step == "room_list":
            self._render_room_list()
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

    def _render_room_list(self) -> None:
        state = self.state
        st.subheader("Choose a room")
        rooms = sorted(
            self.room_service.list_rooms(),
            key=lambda room: (room.started, room.updated_at),
            reverse=True,
        )
        if not rooms:
            st.info("No rooms are available yet.")
            col1, col2 = st.columns(2)
            if col1.button("Back", key="room_list_back_empty"):
                self.reset()
                st.session_state["route"] = "entry"
                common.rerun()
            if col2.button("Refresh", key="room_list_refresh_empty"):
                common.rerun()
            return

        room_options = {room.room_code: room for room in rooms}
        selected_room_code = st.selectbox(
            "Available rooms",
            options=list(room_options.keys()),
            format_func=lambda code: self._format_room_option(room_options[code]),
        )
        selected_room = room_options[selected_room_code]
        common.show_room_summary(selected_room)

        col1, col2, col3 = st.columns(3)
        if col1.button("Back", key="room_list_back"):
            self.reset()
            st.session_state["route"] = "entry"
            common.rerun()
        if col2.button("Refresh", key="room_list_refresh"):
            common.rerun()
        if col3.button("Join room", key="room_list_next"):
            state["candidate_room_code"] = selected_room_code
            if selected_room.started:
                state["selected_player_id"] = None
                state["step"] = "reclaim_player"
                common.rerun()
                return
            state["step"] = "player_name"
            common.rerun()

    def _render_player_name(self) -> None:
        state = self.state
        room_code = state.get("candidate_room_code")
        room = self.room_service.get_room_by_code(room_code) if room_code else None
        if not room:
            st.warning("Room was closed or no longer exists.")
            state["step"] = "room_list"
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
            state["step"] = "room_list"
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
            state["step"] = "room_list"
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
                state["step"] = "room_list"
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
            state["step"] = "room_list"
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
            state["step"] = "room_list"
            state["joined_room_code"] = None
            state["player_id"] = None
            common.rerun()
            return
        if room.started:
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
            common.rerun()
            return
        self._watch_room_updates(room.room_code, room.updated_at.isoformat())
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
            state["step"] = "room_list"
            state["candidate_room_code"] = None
            common.rerun()

    @st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
    def _watch_room_updates(self, room_code: str, known_updated_at: str) -> None:
        """Rerun the page only when the lobby changes."""
        room = self.room_service.get_room_by_code(room_code)
        if not room or room.updated_at.isoformat() != known_updated_at:
            st.rerun()

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

    def _format_room_option(self, room) -> str:
        join_label = common.room_join_label(room)
        visibility = "Private" if room.is_private else "Public"
        status = "In game" if room.started else "Lobby"
        return f"{join_label} | {visibility} | {status} | {len(room.players)} players"
