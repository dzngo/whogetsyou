"""Lightweight helpers that will be expanded for the in-game flow."""

from __future__ import annotations

from models import Room
from services.room_service import RoomService


class GameService:
    """Keeps track of room level game lifecycle hooks."""

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    def start_game(self, room: Room) -> Room:
        room.started = True
        room.update_timestamp()
        self.room_service.repository.save(room)
        return room

    def end_game(self, room: Room) -> Room:
        room.started = False
        room.update_timestamp()
        self.room_service.repository.save(room)
        return room
