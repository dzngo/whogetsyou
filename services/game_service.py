"""Game lifecycle helpers and data management."""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List

from models import (
    Player,
    Room,
)
from services.room_service import RoomService


def _player_scores(players: List[Player]) -> Dict[str, int]:
    return {player.player_id: 0 for player in players}


class GameService:
    """Keeps track of game state stored with the room."""

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    def start_game(self, room: Room) -> Room:
        if len(room.players) < 3:
            raise ValueError("At least three players are required to start the game.")
        order = [player.player_id for player in room.players]
        random.shuffle(order)
        room.started = True
        room.game_state = self._build_initial_state(room, order)
        room.update_timestamp()
        self.room_service.repository.save(room)
        return room

    def set_state(self, room: Room, state: Dict[str, Any]) -> Room:
        room.game_state = copy.deepcopy(state)
        room.update_timestamp()
        self.room_service.repository.save(room)
        return room

    def end_game(self, room: Room) -> Room:
        if (room.game_state or {}).get("question_events_pending"):
            raise RuntimeError("Question statistics are still pending; retry before leaving the game.")
        room.started = False
        room.game_state = {}
        room.update_timestamp()
        self.room_service.repository.save(room)
        return room

    def _build_initial_state(self, room: Room, order: List[str]) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "round": 1,
            "turn_index": 0,
            "storyteller_order": order,
            "phase": "theme_selection",
            "selected_theme": None,
            "selected_level": None,
            "question": None,
            "question_autogen_attempted": False,
            "question_candidates": [],
            "question_candidate_pools": {},
            "current_candidate_index": 0,
            "question_history": {},
            "angle_history": {},
            "question_seen_by_player": {},
            "question_preference_history": {},
            "consecutive_question_skips": 0,
            "assisted_candidate_ids": [],
            "confirmed_question_ids": [],
            "saved_questions_by_player": {},
            "question_events_pending": [],
            "answer_submissions": {},
            "multiple_choice": {"options": []},
            "listener_guesses": {},
            "scores": _player_scores(room.players),
            "max_score": room.settings.max_score,
            "round_summary": None,
            "completed_rounds": [],
            "winners": [],
        }
        return state

    def prepare_next_turn(self, room: Room, advance_round: bool = True) -> Room:
        state = copy.deepcopy(room.game_state or {})
        if not state:
            return room
        if advance_round:
            state["round"] = state.get("round", 1) + 1
            order = state.get("storyteller_order", [])
            if order:
                state["turn_index"] = (state.get("turn_index", 0) + 1) % len(order)
        else:
            state["turn_index"] = state.get("turn_index", 0)

        state["selected_theme"] = None
        state["selected_level"] = None
        state["question"] = None
        state["question_autogen_attempted"] = False
        state["consecutive_question_skips"] = 0
        state["assisted_candidate_ids"] = []
        state["question_candidates"] = []
        state["current_candidate_index"] = 0
        state["answer_submissions"] = {}
        state["multiple_choice"] = {"options": []}
        state["listener_guesses"] = {}
        state["round_summary"] = None
        order = state.get("storyteller_order") or []
        storyteller_id = order[state["turn_index"] % len(order)] if order else None
        saved = (state.get("saved_questions_by_player") or {}).get(storyteller_id, [])
        state["phase"] = "saved_questions" if saved else "theme_selection"
        return self.set_state(room, state)
