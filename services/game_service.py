"""Game lifecycle helpers and data management."""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List

from models import (
    LevelMode,
    Player,
    Room,
    ThemeMode,
)
from services.room_service import RoomService


def _player_scores(players: List[Player]) -> Dict[str, int]:
    return {player.player_id: 0 for player in players}


class GameService:
    """Keeps track of game state stored with the room."""

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    def start_game(self, room: Room) -> Room:
        if len(room.players) < 2:
            raise ValueError("At least two players are required to start the game.")
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
            "phase": None,
            "selected_theme": None,
            "selected_level": room.settings.selected_level.value if room.settings.selected_level else None,
            "question": None,
            "question_autogen_attempted": False,
            "question_history": {},
            "true_answer": None,
            "trap_answer": None,
            "multiple_choice": None,
            "options_autogen_attempted": False,
            "listener_guesses": {},
            "scores": _player_scores(room.players),
            "max_score": room.settings.max_score,
            "round_summary": None,
            "winners": [],
            "static_theme_index": 0,
        }
        state["phase"] = self._initial_phase(room)
        if room.settings.theme_mode == ThemeMode.STATIC:
            state["selected_theme"] = self._resolve_static_theme(room, state, advance_index=True)
        return state

    def _initial_phase(self, room: Room) -> str:
        if room.settings.theme_mode == ThemeMode.DYNAMIC:
            return "theme_selection"
        if room.settings.level_mode == LevelMode.DYNAMIC:
            return "level_selection"
        return "question_generation"

    def _resolve_static_theme(self, room: Room, state: Dict[str, Any], advance_index: bool = True) -> str:
        themes = room.settings.selected_themes or ["Open conversation"]
        index = state.get("static_theme_index", 0) % len(themes)
        theme = themes[index]
        if advance_index:
            state["static_theme_index"] = (index + 1) % len(themes)
        return theme

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
        state["selected_level"] = (
            room.settings.selected_level.value if room.settings.level_mode == LevelMode.STATIC else None
        )
        state["question"] = None
        state["question_autogen_attempted"] = False
        state["true_answer"] = None
        state["trap_answer"] = None
        state["multiple_choice"] = None
        state["options_autogen_attempted"] = False
        state["listener_guesses"] = {}
        state["round_summary"] = None
        if room.settings.theme_mode == ThemeMode.STATIC:
            state["selected_theme"] = self._resolve_static_theme(room, state, advance_index=True)
        state["phase"] = self._initial_phase(room)
        return self.set_state(room, state)
