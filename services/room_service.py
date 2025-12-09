"""Domain logic for creating and maintaining rooms before the game starts."""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from models import (
    GameplayMode,
    LevelMode,
    Player,
    PlayerRole,
    Room,
    RoomSettings,
    ThemeMode,
)
from storage.room_repository import RoomRepository


class RoomServiceError(Exception):
    """Base error for room related operations."""


class RoomNotFoundError(RoomServiceError):
    pass


class RoomAlreadyStartedError(RoomServiceError):
    pass


class InvalidRoomSettingsError(RoomServiceError):
    pass


class RoomService:
    """Handles room lifecycle before the in-game flow begins."""

    def __init__(self, repository: Optional[RoomRepository] = None) -> None:
        self.repository = repository or RoomRepository()

    def get_room_by_code(self, room_code: str) -> Optional[Room]:
        if not room_code:
            return None
        return self.repository.get_by_code(room_code.strip().upper())

    def get_room_by_name(self, name: str) -> Optional[Room]:
        if not name:
            return None
        return self.repository.get_by_name(name)

    def create_room(self, host_name: str, host_email: str, room_name: str, settings: RoomSettings) -> Room:
        """Creates a completely new room with the provided configuration."""
        self._validate_settings(settings)
        now = datetime.utcnow()
        host_player = self._build_player(host_name, host_email, PlayerRole.HOST)
        room = Room(
            room_code=self._generate_room_code(),
            name=room_name.strip(),
            host_id=host_player.player_id,
            host_name=host_player.name,
            created_at=now,
            updated_at=now,
            started=False,
            players=[host_player],
            settings=settings,
        )
        self.repository.save(room)
        return room

    def reuse_room(self, room: Room, host_name: str, host_email: str) -> Room:
        """Resets players for an existing room while keeping configuration."""
        host_player = self._build_player(host_name, host_email, PlayerRole.HOST)
        room.host_id = host_player.player_id
        room.host_name = host_player.name
        room.players = [host_player]
        room.started = False
        room.update_timestamp()
        self.repository.save(room)
        return room

    def reconfigure_room(self, room: Room, host_name: str, host_email: str, settings: RoomSettings) -> Room:
        """Keeps the room code/name but overwrites settings."""
        self._validate_settings(settings)
        host_player = self._build_player(host_name, host_email, PlayerRole.HOST)
        room.host_id = host_player.player_id
        room.host_name = host_player.name
        room.players = [host_player]
        room.started = False
        room.settings = settings
        room.update_timestamp()
        self.repository.save(room)
        return room

    def add_player(self, room: Room, player_name: str, player_email: str) -> Player:
        """Adds a listener to a room if the game hasn't started."""
        if room.started:
            raise RoomAlreadyStartedError(f"Room {room.room_code} has already started the game.")
        normalized_email = player_email.strip().lower()
        for existing in room.players:
            if existing.email.strip().lower() == normalized_email:
                existing.name = player_name.strip() or existing.name
                existing.is_connected = True
                room.update_timestamp()
                self.repository.save(room)
                return existing
        player = self._build_player(player_name, player_email, PlayerRole.JOINER)
        room.players.append(player)
        room.update_timestamp()
        self.repository.save(room)
        return player

    def adjust_gameplay_mode(self, room: Room, gameplay_mode: GameplayMode) -> Room:
        room.settings.gameplay_mode = gameplay_mode
        room.update_timestamp()
        self.repository.save(room)
        return room

    def update_max_score(self, room: Room, max_score: int) -> Room:
        if max_score < 1:
            raise InvalidRoomSettingsError("Max score must be a positive number.")
        room.settings.max_score = max_score
        room.update_timestamp()
        self.repository.save(room)
        return room

    def remove_player(self, room: Room, player_id: str) -> Room:
        """Removes a player from the room roster if present."""
        filtered = [player for player in room.players if player.player_id != player_id]
        if len(filtered) == len(room.players):
            return room
        room.players = filtered
        room.update_timestamp()
        self.repository.save(room)
        return room

    def _generate_room_code(self) -> str:
        alphabet = string.ascii_uppercase
        while True:
            code = "".join(random.choices(alphabet, k=5))
            if not self.repository.get_by_code(code):
                return code

    def _build_player(self, name: str, email: str, role: PlayerRole) -> Player:
        cleaned = name.strip()
        cleaned_email = email.strip().lower()
        if not cleaned:
            raise ValueError("Player name cannot be empty.")
        if not cleaned_email:
            raise ValueError("Email is required.")
        return Player(
            player_id=str(uuid.uuid4()),
            name=cleaned,
            email=cleaned_email,
            role=role,
            joined_at=datetime.utcnow(),
        )

    def _validate_settings(self, settings: RoomSettings) -> None:
        if settings.theme_mode == ThemeMode.STATIC and not settings.selected_themes:
            raise InvalidRoomSettingsError("At least one theme must be selected for static theme mode.")
        if settings.level_mode == LevelMode.STATIC and not settings.selected_level:
            raise InvalidRoomSettingsError("A specific level is required when level mode is static.")
        if settings.max_score < 1:
            raise InvalidRoomSettingsError("Max score must be greater than zero.")

    def list_rooms(self) -> List[Room]:
        return self.repository.list_rooms()

    def find_player_memberships(self, email: str) -> List[Tuple[Room, Player]]:
        normalized = email.strip().lower()
        if not normalized:
            return []
        matches: List[Tuple[Room, Player]] = []
        for room in self.list_rooms():
            for player in room.players:
                if player.email.strip().lower() == normalized:
                    matches.append((room, player))
        return matches
