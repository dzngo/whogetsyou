"""Streamlit helpers shared between host and join flows."""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from models import Room


def get_flow_state(key: str, *, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a mutable dict stored in session_state under ``key``."""
    if key not in st.session_state:
        st.session_state[key] = defaults.copy()
    return st.session_state[key]


def reset_flow_state(key: str, *, defaults: Dict[str, Any]) -> None:
    st.session_state[key] = defaults.copy()


def go_home() -> None:
    st.session_state["route"] = "entry"


def rerun() -> None:
    """Trigger a Streamlit rerun while supporting older versions."""
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()
    else:
        getattr(st, "experimental_rerun")()


def show_room_summary(room: Room) -> None:
    st.subheader("Room summary")
    st.write(f"**Room name:** {room.name}")
    st.write(f"**Room code:** `{room.room_code}`")
    settings = room.settings
    theme_desc = settings.theme_mode.value.title()
    if settings.theme_mode.value == "static" and settings.selected_themes:
        theme_desc += f" ({', '.join(settings.selected_themes)})"
    level_desc = settings.level_mode.value.title()
    if settings.level_mode.value == "static" and settings.selected_level:
        level_desc += f" ({settings.selected_level.value.title()})"
    st.write(f"**Gameplay mode:** {settings.gameplay_mode.value.title()}")
    st.write(f"**Theme mode:** {theme_desc}")
    st.write(f"**Level mode:** {level_desc}")
    st.write(f"**Max score:** {settings.max_score}")
    st.markdown("**Players:**")
    for player in room.players:
        role = "Host" if player.role.value == "host" else "Player"
        st.write(f"- {player.name} ({role})")
