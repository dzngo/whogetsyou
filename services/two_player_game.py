"""Scoring and statistics for two-player games."""

from __future__ import annotations


def judge_answer(state: dict, storyteller_id: str, listener_id: str, correct: bool) -> None:
    """Record one judgment exactly once, then check the target after both turns."""
    if state.get("round_summary"):
        return
    submissions = state.get("answer_submissions") or {}
    if (
        storyteller_id == listener_id
        or not str(submissions.get(storyteller_id) or "").strip()
        or not str(submissions.get(listener_id) or "").strip()
    ):
        raise ValueError("Both players must submit answers before judgment.")
    level = state.get("selected_level")
    if level not in ("shallow", "deep"):
        raise ValueError("A valid question level is required.")
    points = (1 if level == "shallow" else 3) if correct else 0
    scores = state.setdefault("scores", {})
    scores[listener_id] = scores.get(listener_id, 0) + points
    record = {
        "round": state.get("round", 1),
        "storyteller_id": storyteller_id,
        "listener_id": listener_id,
        "level": level,
        "correct": correct,
        "points": points,
        "theme": state.get("selected_theme"),
    }
    completed = state.setdefault("completed_rounds", [])
    completed.append(record)
    turns = {pid: sum(item.get("listener_id") == pid for item in completed) for pid in scores}
    winners = []
    if turns and len(set(turns.values())) == 1 and max(scores.values()) >= state["max_score"]:
        high = max(scores.values())
        winners = [pid for pid, score in scores.items() if score == high]
    state["round_summary"] = {"correct": correct, "listener_id": listener_id, "points": points, "winners": winners}
    state["phase"] = "reveal"


def player_statistics(state: dict, player_id: str) -> dict:
    rounds = [round_ for round_ in state.get("completed_rounds", []) if round_.get("listener_id") == player_id]
    correct = [round_ for round_ in rounds if round_.get("correct")]
    return {
        "turns": len(rounds),
        "correct": len(correct),
        "accuracy": len(correct) / len(rounds) if rounds else None,
        "shallow": sum(round_.get("level") == "shallow" for round_ in correct),
        "deep": sum(round_.get("level") == "deep" for round_ in correct),
    }
