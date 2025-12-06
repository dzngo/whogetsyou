"""Streamlit helpers shared between host and join flows."""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st
from streamlit.components.v1 import html as components_html

from models import Room, SUPPORTED_LANGUAGES


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
    language = SUPPORTED_LANGUAGES.get(settings.language.lower(), settings.language)
    st.write(f"**Language:** {language}")
    st.markdown("**Players:**")
    for player in room.players:
        role = "Host" if player.role.value == "host" else "Player"
        st.write(f"- {player.name} ({role})")


def style_buttons() -> None:
    """Inject client-side styling for key button categories."""
    components_html(
        """
        <script>
        (function() {
          const root = window.parent?.document;
          if (!root) return;
          const warnColor = '#000000';
          const positiveColor = '#0f9d58';
          const dangerColor = '#c52233';
          const confirmColor = '#1a73e8';
          const aiColor = '#ea8600';
          const paint = () => {
            const buttons = root.querySelectorAll('button');
            buttons.forEach((btn) => {
              const label = btn.innerText.replace(/\\s+/g, ' ').trim().toLowerCase();
              if (!label) return;
              let bg = '';
              if (['end game', 'force reveal'].includes(label)) {
                bg = warnColor;
              } else if (label.includes('back') || label.includes('change room') || label.includes('return')) {
                bg = dangerColor;
              } else if (
                label.includes('confirm') || 
                label.includes('submit') || 
                label.includes('start') || 
                label.includes('join') || 
                label.includes('reuse') || 
                label.includes('change settings')
              ) {
                bg = confirmColor;
              } else if (label.includes('next') || label.includes('refresh') || label.includes('create')) {
                bg = positiveColor;
              } else if (
                label.includes('suggest') ||
                label.includes('change question') ||
                label.includes('change options')
              ) {
                bg = aiColor;
              }
              if (bg) {
                btn.style.backgroundColor = bg;
                btn.style.borderColor = bg;
                btn.style.color = '#ffffff';
              }
            });
          };
          const key = '__wg_button_observer';
          if (root[key]) {
            try { root[key].disconnect(); } catch (err) {}
          }
          const observer = new MutationObserver(() => paint());
          observer.observe(root.body, { childList: true, subtree: true });
          root[key] = observer;
          setTimeout(paint, 0);
        })();
        </script>
        """,
        height=0,
    )
