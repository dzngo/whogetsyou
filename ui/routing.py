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
        - **Storyteller** - chooses the question, writes their honest answer, and in Bluffing mode also writes a believable fake answer (the “trap”).
        - **Listeners** - read all the options and select the one they believe is the Storyteller's true answer.

        ---

        ### How a round works
        1. **Pick the vibe** - The host or Storyteller chooses the theme and depth (shallow / medium / deep). Deeper rounds are worth more points.
        2. **Get a question** - A question is proposed; the Storyteller can edit it or ask for a new one.
        3. **Write answers**  
           - **Simple mode**: Storyteller writes just their real answer.  
           - **Bluffing mode**: Storyteller writes a real answer *and* a fake but plausible answer.
        4. **Build the options** - The app turns those answers into multiple-choice options (real answer, trap if used, plus distractors). The Storyteller checks that everything looks fair.
        5. **Everyone guesses** - Listeners choose the option they think is real.
        6. **Reveal & points** - The real answer is shown, who guessed what is revealed, and everyone gains points based on depth and how tricky the round was.

        ---

        ### Scoring rules
        - **Depth multiplier** - Shallow = x1, Medium = x2, Deep = x3. All points below are multiplied by this.
        - **Simple mode**
          - Each correct Listener guess: **+1 x depth**.
          - If some (but not all) Listeners are correct: Storyteller **+1 x depth**.
          - If everyone is correct: Storyteller **+2 x depth**.
        - **Bluffing mode**
          - Exactly one Listener correct: that Listener **+3 x depth**, Storyteller **+3 x depth**.
          - Some (but not all) correct: each correct Listener **+1 x depth**, Storyteller **+1 x depth**.
          - Everyone correct: each Listener **+2 x depth**, Storyteller **0**.

        ---

        ### How to win
        - Deeper questions (Medium / Deep) give bigger point rewards.
        - In Simple mode, everyone is just trying to match the real answer; correct guesses give points to both Listeners and the Storyteller, with a bonus when *everyone* gets it.
        - In Bluffing mode, Listeners want to find the real answer, while the Storyteller wants at least some people to fall for the trap without losing *everyone*.
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
