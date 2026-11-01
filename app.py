import streamlit as st
from dotenv import load_dotenv


from ui import routing
from storage.question_events import QuestionEvents
from services.question_bank import load_questions

load_dotenv()


@st.cache_resource(show_spinner=False)
def initialize_question_counters(environment: str, questions: tuple[tuple[str, str], ...]) -> bool:
    QuestionEvents(environment=environment).initialize(questions)
    return True


def main() -> None:
    st.set_page_config(
        page_title="Who Gets You?",
        page_icon="🎭",
        layout="centered",
    )
    import os

    try:
        initialize_question_counters(
            os.getenv("WGY_ENV", "development"), tuple((question["id"], question["text"]) for question in load_questions())
        )
    except Exception:
        st.warning("Question statistics are unavailable. They will be retried when the database is available.")
    routing.run()


if __name__ == "__main__":
    main()
