"""Core dataclasses and enums representing the Who Gets You pre-game domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class GameplayMode(str, Enum):
    """Gameplay variations supported by the specification."""

    SIMPLE = "simple"
    BLUFFING = "bluffing"


class ThemeMode(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class LevelMode(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class Level(str, Enum):
    NARROW = "narrow"
    MEDIUM = "medium"
    DEEP = "deep"


class PlayerRole(str, Enum):
    HOST = "host"
    JOINER = "joiner"


DEFAULT_THEMES: List[str] = [
    "Childhood",
    "Travel",
    "Work",
    "Relationships",
    "Hobbies",
    "Family",
    "Dreams",
]


def _iso_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class Player:
    player_id: str
    name: str
    role: PlayerRole
    joined_at: datetime
    is_connected: bool = True

    def to_dict(self) -> Dict[str, str]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "is_connected": self.is_connected,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Player":
        return cls(
            player_id=data["player_id"],
            name=data["name"],
            role=PlayerRole(data["role"]),
            joined_at=_iso_to_datetime(data["joined_at"]),
            is_connected=data.get("is_connected", True),
        )


@dataclass
class RoomSettings:
    theme_mode: ThemeMode = ThemeMode.DYNAMIC
    selected_themes: List[str] = field(default_factory=list)
    level_mode: LevelMode = LevelMode.DYNAMIC
    selected_level: Optional[Level] = None
    gameplay_mode: GameplayMode = GameplayMode.SIMPLE
    max_score: int = 100

    def to_dict(self) -> Dict[str, object]:
        return {
            "theme_mode": self.theme_mode.value,
            "selected_themes": list(self.selected_themes),
            "level_mode": self.level_mode.value,
            "selected_level": self.selected_level.value if self.selected_level else None,
            "gameplay_mode": self.gameplay_mode.value,
            "max_score": self.max_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "RoomSettings":
        return cls(
            theme_mode=ThemeMode(data["theme_mode"]),
            selected_themes=list(data.get("selected_themes", [])),
            level_mode=LevelMode(data["level_mode"]),
            selected_level=Level(data["selected_level"]) if data.get("selected_level") else None,
            gameplay_mode=GameplayMode(data["gameplay_mode"]),
            max_score=int(data.get("max_score", 100)),
        )


@dataclass
class Room:
    room_code: str
    name: str
    host_id: str
    host_name: str
    created_at: datetime
    updated_at: datetime
    started: bool = False
    players: List[Player] = field(default_factory=list)
    settings: RoomSettings = field(default_factory=RoomSettings)
    game_state: Dict[str, Any] = field(default_factory=dict)

    def update_timestamp(self) -> None:
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, object]:
        return {
            "room_code": self.room_code,
            "name": self.name,
            "host_id": self.host_id,
            "host_name": self.host_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started": self.started,
            "players": [player.to_dict() for player in self.players],
            "settings": self.settings.to_dict(),
            "game_state": self.game_state,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Room":
        return cls(
            room_code=data["room_code"],
            name=data["name"],
            host_id=data["host_id"],
            host_name=data.get("host_name", ""),
            created_at=_iso_to_datetime(data["created_at"]),
            updated_at=_iso_to_datetime(data["updated_at"]),
            started=bool(data.get("started", False)),
            players=[Player.from_dict(player_data) for player_data in data.get("players", [])],
            settings=RoomSettings.from_dict(data["settings"]),
            game_state=dict(data.get("game_state", {})),
        )
