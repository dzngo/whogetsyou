"""Streamlit router handling entry → host/join flows."""

from __future__ import annotations

import re
from typing import Dict, Optional

import streamlit as st
from textwrap import dedent

from services.game_service import GameService
from services.llm_service import LLMService
from services.room_service import RoomService
from services.user_service import UserAccount, UserService
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
        self.user_service = UserService()
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
        if not self._ensure_identity():
            return
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
        profile = st.session_state.get("user_profile")
        if profile:
            st.caption(f"Signed in as **{profile['name']}** ({profile['email']})")
        st.write("Start by choosing whether you want to host a room or join an existing game.")
        col1, col2, col3 = st.columns(3)
        if col1.button("Create room", key="entry_create"):
            st.session_state["route"] = "host"
            common.rerun()
        if col2.button("Join room", key="entry_join"):
            st.session_state["route"] = "join"
            common.rerun()
        if col3.button("Switch account", key="entry_switch_account"):
            for key in (
                "user_profile",
                "player_profile",
                "active_room_code",
                "identity_conflict",
                "identity_resume_checked",
            ):
                st.session_state.pop(key, None)
            st.session_state["route"] = "entry"
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

    def _ensure_identity(self) -> bool:
        profile = st.session_state.get("user_profile")
        if profile:
            if not st.session_state.get("identity_resume_checked"):
                self._attempt_auto_resume()
            return True

        st.subheader("Identify yourself")
        st.write("Connect with your email to resume games or create a new account if this is your first time.")

        tab_connect, tab_create = st.tabs(["Connect", "Create account"])

        with tab_connect:
            with st.form("identity_connect_form"):
                email = st.text_input("Email", key="identity_connect_email")
                submitted = st.form_submit_button("Connect")
            if submitted:
                account = self.user_service.get(email)
                if not account:
                    st.error("No account found with that email. Please create one.")
                else:
                    self._complete_identity(account)
                    return False

        with tab_create:
            with st.form("identity_create_form"):
                email_new = st.text_input("Email", key="identity_create_email")
                name_new = st.text_input("Display name", key="identity_create_name")
                submitted_new = st.form_submit_button("Create account")
            if submitted_new:
                email_clean = email_new.strip().lower()
                name_clean = name_new.strip()
                if not email_clean or not name_clean:
                    st.error("Please enter both email and name.")
                elif not self._is_valid_email(email_clean):
                    st.error("Please enter a valid email address (example: name@example.com).")
                else:
                    existing = self.user_service.get(email_clean)
                    if existing:
                        st.warning(
                            f"{email_clean} is already associated with **{existing.name}**. "
                            "If this is you, confirm below."
                        )
                        st.session_state["identity_conflict"] = existing.to_dict()
                    else:
                        account = self.user_service.create(email_clean, name_clean)
                        self._complete_identity(account)
                        return False
            conflict = st.session_state.get("identity_conflict")
            expected_email = email_new.strip().lower()
            if conflict and conflict.get("email", "").lower() != expected_email:
                conflict = None
            if conflict:
                st.info(
                    f"This email is currently used by **{conflict['name']}**. " "If that's you, confirm to continue."
                )
                col_confirm, col_cancel = st.columns(2)
                if col_confirm.button("Yes, that's me", key="identity_claim_existing"):
                    account = UserAccount.from_dict(conflict)
                    self._complete_identity(account)
                    return False
                if col_cancel.button("Not me", key="identity_conflict_cancel"):
                    st.session_state.pop("identity_conflict", None)

        with st.expander(":arrow_down: Game rules", expanded=False):
            st.markdown(self.RULES_SUMMARY)

        return False

    @staticmethod
    def _is_valid_email(value: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))

    def _complete_identity(self, account: UserAccount) -> None:
        st.session_state["user_profile"] = {
            "email": account.email,
            "name": account.name,
        }
        st.session_state.pop("identity_conflict", None)
        st.session_state.pop("player_profile", None)
        if not self._attempt_auto_resume(account):
            common.rerun()

    def _attempt_auto_resume(self, account: Optional[UserAccount | Dict[str, str]] = None) -> bool:
        st.session_state["identity_resume_checked"] = True
        data: Optional[Dict[str, str]] = None
        if isinstance(account, UserAccount):
            data = {"email": account.email, "name": account.name}
        elif isinstance(account, dict):
            data = account
        else:
            data = st.session_state.get("user_profile")
        if not data:
            return False
        email = data.get("email", "").strip().lower()
        if not email:
            return False
        for room, player in self.room_service.find_player_memberships(email):
            if not room.started:
                continue
            st.session_state["player_profile"] = {
                "player_id": player.player_id,
                "room_code": room.room_code,
                "name": player.name,
                "email": player.email,
            }
            st.session_state["active_room_code"] = room.room_code
            st.session_state["route"] = "game"
            st.success("Welcome back! Reconnecting you to your game...")
            common.rerun()
            return True
        return False


def run() -> None:
    Router().render()
