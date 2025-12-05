"""Streamlit router handling entry → host/join flows."""

from __future__ import annotations

import streamlit as st

from services.llm_service import LLMService
from services.room_service import RoomService
from ui import common
from ui.host_flow import HostFlow
from ui.join_flow import JoinFlow


class Router:
    def __init__(self) -> None:
        self.room_service = RoomService()
        self.llm_service = LLMService()
        self.host_flow = HostFlow(self.room_service, self.llm_service)
        self.join_flow = JoinFlow(self.room_service)

    def render(self) -> None:
        if "route" not in st.session_state:
            st.session_state["route"] = "entry"
        route = st.session_state["route"]
        st.title("Who Gets You? - Pre-game")
        if route == "entry":
            self._render_entry()
        elif route == "host":
            self.host_flow.render()
        elif route == "join":
            self.join_flow.render()
        else:
            st.session_state["route"] = "entry"
            common.rerun()

    def _render_entry(self) -> None:
        st.subheader("Screen 0 – Entry")
        st.write("Start by choosing whether you want to host a room or join an existing game.")
        col1, col2 = st.columns(2)
        if col1.button("Create room", key="entry_create"):
            st.session_state["route"] = "host"
            common.rerun()
        if col2.button("Join room", key="entry_join"):
            st.session_state["route"] = "join"
            common.rerun()


def run() -> None:
    Router().render()
