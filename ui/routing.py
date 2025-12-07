"""Streamlit router handling entry → host/join flows."""

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
        There are two roles in each round:
        - **Storyteller** – answers the prompt and, in Bluffing mode, supplies a believable trap.
        - **Listeners** – study the Storyteller’s options and vote for the one they believe is true.

        ---

        ### Objective
        Earn points by understanding your friends, spotting traps, and making accurate guesses.  
        The first player to reach the target score (or the leader when the host ends the session) wins.

        ---

        ### Setup
        - The host chooses gameplay mode (Simple or Bluffing), theme mode (Static rotation or Dynamic per turn), level mode (Narrow/Medium/Deep, static or dynamic), and the target score.  
        - Players join via room code and the storyteller order is randomly locked in.

        ### Turn Loop
        1. Storyteller locks the theme and depth if the room uses dynamic modes.  
        2. A single open-ended question is proposed; it can be edited or regenerated.  
        3. Storyteller confirms the honest answer (and a trap answer in Bluffing mode).  
        4. Multiple-choice options (true answer, trap if applicable, plus distractors) are generated and confirmed.  
        5. Listeners submit their guesses.  
        6. Reveal shows the true answer, highlights trap hits, and awards points using depth multipliers (Narrow = ×1, Medium = ×2, Deep = ×3).

        ### Scoring Snapshot
        - **Depth multipliers** – Narrow = ×1, Medium = ×2, Deep = ×3. Multiply every value below by the current depth.
        - **Simple mode**
            - Each correct Listener guess: **+1× depth**.
            - Storyteller earns **+1× depth** if some (but not all) Listeners are correct.
            - Storyteller earns **+2× depth** if everyone is correct.
        - **Bluffing mode**
            - Exactly one Listener correct: that Listener and the Storyteller both gain **+3× depth**.
            - Some (but not all) correct: every correct Listener **+1× depth**, Storyteller **+1× depth**.
            - Everyone correct: each Listener **+2× depth**, Storyteller **+0**.
            - Nobody correct (trap or distractors): **0** for everyone, but the Storyteller can still celebrate fooling the room.
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
        title = "Who Gets You? 🎭 - In-game" if route == "game" else "Who Gets You? 🎭 - Pre-game"
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
