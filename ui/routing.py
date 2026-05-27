"""Streamlit router handling entry -> host/join/game flows."""

from __future__ import annotations

import streamlit as st
from textwrap import dedent

from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
from ui import common
from ui.game_flow import GameFlow
from ui.host_flow import HostFlow
from ui.join_flow import JoinFlow


class Router:
    RULES_SUMMARY = dedent(
        """
        ### Roles
        - **Storyteller** - chooses the theme, level, and final question, then submits the Storyteller answer.
        - **Listeners** - submit plausible answers, then guess which answer belongs to the Storyteller.

        ---

        ### How a round works
        1. **Pick the vibe** - The Storyteller chooses a theme and level: Shallow or Deep.
        2. **Get a question** - A question is proposed; the Storyteller can edit it or ask for a new one.
        3. **Write answers** - Every player submits one answer to the same question.
        4. **Everyone guesses** - Listeners choose the answer they think belongs to the Storyteller.
        5. **Reveal & points** - The Storyteller answer is shown, guesses are revealed, and points are awarded.

        ---

        ### Question styles
        - **Shallow** - funny, quick, low-pressure questions. Expect playful hypotheticals, silly choices, and imagined situations.
        - **Deep** - reflective, emotionally safe questions about memories, values, relationships, beliefs, hopes, or self-understanding.
        - **Random theme** - a wildcard theme for surprising questions.

        ---

        ### Scoring rules
        - **Depth multiplier** - Shallow = x1, Deep = x2.
        - **Exactly one Listener guesses the Storyteller answer**: that Listener **+3 x depth**, Storyteller **+3 x depth**.
        - **Some but not all Listeners guess it**: each correct Listener **+1 x depth**, Storyteller **+1 x depth**.
        - **Everyone or nobody guesses it**: each Listener **+2 x depth**, Storyteller **0**.
        - **Decoy bonus**: if a Listener's submitted answer is chosen by N other Listeners, that Listener gets **+N x depth**.

        ---

        ### How to win
        - The game ends when someone reaches the target score (or the host ends the session). The highest score wins.
        """
    ).strip()

    def __init__(self) -> None:
        self.room_service = RoomService()
        self.game_service = GameService(self.room_service)
        self.llm_service = LLMService()
        self.game_flow = GameFlow(self.room_service, self.game_service, self.llm_service)
        self.host_flow = HostFlow(self.room_service, self.llm_service, self.game_service)
        self.join_flow = JoinFlow(self.room_service)

    def render(self) -> None:
        if "route" not in st.session_state:
            st.session_state["route"] = "entry"
        route = st.session_state["route"]
        title = "Who Gets You? 🎭 "
        st.title(title)
        common.style_buttons()
        if route == "entry":
            self._render_entry()
        elif route == "host":
            self.host_flow.render()
        elif route == "join":
            self.join_flow.render()
        elif route == "game":
            self._ensure_game_llm()
            self.game_flow.render()
        else:
            st.session_state["route"] = "entry"
            common.rerun()

    def _render_entry(self) -> None:
        st.subheader("Welcome")
        st.write("Start by choosing whether you want to host a room or join an existing game.")
        col1, col2 = st.columns(2)
        if col1.button("Create room", key="entry_create"):
            st.session_state["route"] = "host"
            common.rerun()
        if col2.button("Join room", key="entry_join"):
            st.session_state["route"] = "join"
            common.rerun()
        show_rules = st.session_state.get("show_rules_panel", False)
        if st.button("View game rules", key="entry_rules"):
            show_rules = True
            st.session_state["show_rules_panel"] = True
        if show_rules:
            with st.expander("Game rules", expanded=True):
                st.markdown(self.RULES_SUMMARY)
                if st.button("Hide rules", key="entry_hide_rules"):
                    st.session_state["show_rules_panel"] = False
                    common.rerun()

    def _ensure_game_llm(self) -> None:
        room_code = st.session_state.get("active_room_code")
        if not room_code:
            return
        room = self.room_service.get_room_by_code(room_code)
        if not room:
            return
        target_model = getattr(room.settings, "llm_model", None) or "gpt-4o-mini"
        current_model = getattr(getattr(self.game_flow.llm_service, "_llm", None), "model_name", None)
        if current_model == target_model:
            return
        self.game_flow.llm_service = LLMService(llm_name=target_model)


def run() -> None:
    Router().render()
