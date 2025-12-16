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
    SHALLOW = "shallow"
    MEDIUM = "medium"
    DEEP = "deep"


class PlayerRole(str, Enum):
    HOST = "host"
    JOINER = "joiner"


DEFAULT_THEMES: List[str] = [
    "Yourself 🌱",
    "Childhood 👶",
    "Family 🏡",
    "Goals ✨",
    "Work 💼",
    "Love 💖",
    "Friends 🤝",
    "Hobbies 🎨",
    "Travel ✈️",
]

THEME_DESCRIPTIONS: Dict[str, str] = {
    "Yourself 🌱": "Self-awareness, snapshots from personal daily life, facts about you, your interests, how you understand yourself, "
    "identity shifts, self-talk, and micro-habits that reveal who you are.",
    "Childhood 👶": "Memories, lessons, and stories from your early years or upbringing that cover family dynamics, formative friendships, "
    "caretakers, and big kid feelings.",
    "Family 🏡": "Experiences with family members, easy moments, the support, the messy parts too, plus traditions, conflict repair, "
    "generational expectations, and how you set boundaries,facts about specific family members, facts about you within your family role, "
    "and the little quirks that define your home life.",
    "Goals ✨": "Dreams you're actively pursuing and milestones you want to reach, including career leaps,"
    " health quests, creative ambitions, and bucket-list experiments.",
    "Work 💼": "Professional life including coworkers, relationships with managers, how you show up on the job, and challenges at "
    "work—dive into team dynamics, promotions, burnout recovery, and leadership style.",
    "Love 💖": "Romantic relationships, intimacy, how you show love to a partner, dating history, love languages, green/red flags, "
    "communication styles, conflict repair, and what you want next (commitment, freedom, stability, adventure) or fact about your partner",
    "Friends 🤝": "Friendship stories (old or new), chosen family moments, and the support you get or give alongside how you met, "
    "inside jokes, fun facts about your friends, loyalty tests, boundaries, rituals of care, and long-distance bonds.",
    "Hobbies 🎨": "Passions, creative outlets, and how you unwind or express yourself by talking through learning curves, the "
    "communities around your craft, resources you lean on, and dream collaborations.",
    "Travel ✈️": "Journeys, discoveries, and how exploring reshapes your worldview with space for planning quirks, culture shocks,"
    " travel buddies, and the lessons that stuck with you.",
}

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "vn": "Tiếng Việt",
    "fr": "Français",
    "es": "Español",
    "de": "Deutsch",
}

LANGUAGE_FLAGS: Dict[str, str] = {
    "en": "🇬🇧",
    "vn": "🇻🇳",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "de": "🇩🇪",
}

SUPPORTED_OPENAI_LLM_MODELS: Dict[str, str] = {
    "gpt-4o-mini": "OpenAI GPT-4o Mini",
    "gpt-4.1-nano": "OpenAI GPT-4.1 Nano",
    "gpt-5-mini	": "OpenAI GPT-5 Mini",
    "gpt-4o": "OpenAI GPT-4o",
    "gpt-4.1-mini": "OpenAI GPT-4.1 Mini",
    "gpt-4.1": "OpenAI GPT-4.1",
}

SUPPORTED_GEMINI_LLM_MODELS: Dict[str, str] = {
    "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
}
SUPPORTED_LLM_MODELS: Dict[str, str] = SUPPORTED_OPENAI_LLM_MODELS | SUPPORTED_GEMINI_LLM_MODELS


def _iso_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class Player:
    player_id: str
    name: str
    email: str
    role: PlayerRole
    joined_at: datetime
    is_connected: bool = True

    def to_dict(self) -> Dict[str, str]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "is_connected": self.is_connected,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Player":
        return cls(
            player_id=data["player_id"],
            name=data["name"],
            email=data.get("email", ""),
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
    language: str = "en"
    llm_model: str = "gemini-2.5-flash"

    def to_dict(self) -> Dict[str, object]:
        return {
            "theme_mode": self.theme_mode.value,
            "selected_themes": list(self.selected_themes),
            "level_mode": self.level_mode.value,
            "selected_level": self.selected_level.value if self.selected_level else None,
            "gameplay_mode": self.gameplay_mode.value,
            "max_score": self.max_score,
            "language": self.language,
            "llm_model": self.llm_model,
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
            language=str(data.get("language", "en")),
            llm_model=str(data.get("llm_model", "gemini-2.5-flash")),
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


@dataclass
class UserAccount:
    email: str
    name: str
    created_at: datetime

    def to_dict(self) -> Dict[str, str]:
        return {
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "UserAccount":
        return cls(
            email=data["email"],
            name=data["name"],
            created_at=_iso_to_datetime(data["created_at"]),
        )
