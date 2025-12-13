"""Streamlit helpers shared between host and join flows."""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st
from streamlit.components.v1 import html as components_html

from models import LANGUAGE_FLAGS, Room, SUPPORTED_LANGUAGES, SUPPORTED_LLM_MODELS


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


def show_room_summary(room: Room, display_llm: bool = False) -> None:
    st.markdown(f"### Room :blue-background[*{room.name}*]")
    with st.container(border=True):
        columns = st.columns(2)
        with columns[0]:
            st.write(f"**Room code:** `{room.room_code}`")
            settings = room.settings
            theme_desc = settings.theme_mode.value.title()
            if settings.theme_mode.value == "static" and settings.selected_themes:
                theme_desc += f" ({', '.join(settings.selected_themes)})"
            level_desc = settings.level_mode.value.title()
            if settings.level_mode.value == "static" and settings.selected_level:
                level_desc += f" ({settings.selected_level.value.title()})"
            st.write(f"**Max score:** {settings.max_score}")
            language_name = SUPPORTED_LANGUAGES.get(settings.language.lower(), settings.language.upper())
            flag = LANGUAGE_FLAGS.get(settings.language.lower(), "")
            language_display = f"{flag} {language_name}".strip()
            st.write(f"**Language:** {language_display}")
            llm_display = SUPPORTED_LLM_MODELS.get(settings.llm_model, settings.llm_model)
            if display_llm:
                st.write(f"**Assistant:** {llm_display}")

        with columns[1]:
            st.write(f"**Theme mode:** {theme_desc}")
            st.write(f"**Level mode:** {level_desc}")
            st.write(f"**Gameplay mode:** {settings.gameplay_mode.value.title()}")


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
          const magicColor = '#a73ac9';
          const loveColor = '#cd0487' ;
          const paint = () => {
            const buttons = root.querySelectorAll('button');
            buttons.forEach((btn) => {
              const label = btn.innerText.replace(/\\s+/g, ' ').trim().toLowerCase();
              if (!label) return;
              let bg = '';
              if (['end game', 'force reveal'].includes(label)) {
                bg = warnColor;
              } else if (
                label.includes('back') || 
                label.includes('change room') || 
                label.includes('return') ||
                label.includes('switch account') ||
                label.includes('report')
              ) {
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
              } else if (label.includes('next') || label.includes('refresh') || label.includes('create room')) {
                bg = positiveColor;
              } else if (
                label.includes('suggest') ||
                label.includes('change question') ||
                label.includes('regenerate')
              ) {
                bg = aiColor;
              } else if (label.includes('like')
              ) {
                bg = loveColor;
              } else if (
                label.includes('rephrase')
              ) {
                bg = magicColor;
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
