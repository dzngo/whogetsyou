"""Entry point for the Who Gets You pre-game prototype."""

import streamlit as st

from ui import routing


def main() -> None:
    st.set_page_config(
        page_title="Who Gets You?",
        page_icon="🎲",
        layout="centered",
    )
    routing.run()


if __name__ == "__main__":
    main()
