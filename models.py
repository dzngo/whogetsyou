"""Core dataclasses and enums representing the Who Gets You pre-game domain."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Level(str, Enum):
    SHALLOW = "shallow"
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

THEME_DESCRIPTIONS: Dict[str, List[str]] = {
    "Yourself 🌱": [
        "Self-awareness and identity shifts",
        "Snapshots from your personal daily life",
        "Facts about you and your interests",
        "How you understand yourself",
        "Self-talk and inner dialogue",
        "Micro-habits that reveal who you are",
    ],
    "Childhood 👶": [
        "Memories and stories from your early years",
        "Lessons from your upbringing",
        "Family dynamics when you were growing up",
        "Formative childhood friendships",
        "Caretakers and their impact on you",
        "Big feelings from kid years",
    ],
    "Family 🏡": [
        "Experiences with family members",
        "Warm and messy family moments",
        "Traditions and rituals at home",
        "Conflict and repair in family life",
        "Generational expectations and boundaries",
        "Quirks that define your home life",
    ],
    "Goals ✨": [
        "Dreams you are actively pursuing",
        "Milestones you want to reach",
        "Career leaps you are aiming for",
        "Health goals and personal growth quests",
        "Creative ambitions",
        "Bucket-list experiments",
    ],
    "Work 💼": [
        "How you show up professionally",
        "Coworker and manager relationships",
        "Team dynamics and collaboration",
        "Challenges and pressure at work",
        "Leadership style and growth",
        "Promotion or burnout recovery stories",
    ],
    "Love 💖": [
        "Romantic relationships and intimacy",
        "How you show love to a partner",
        "Dating history and patterns",
        "Love languages and communication styles",
        "Conflict repair in relationships",
        "What you want next in love",
    ],
    "Friends 🤝": [
        "Friendship stories old and new",
        "Chosen-family moments",
        "How you support and are supported",
        "Inside jokes and shared rituals",
        "Boundaries and loyalty in friendships",
        "Long-distance friendship dynamics",
    ],
    "Hobbies 🎨": [
        "Passions and creative outlets",
        "How you unwind and recharge",
        "Learning curves in your craft",
        "Communities around your hobbies",
        "Resources you lean on to improve",
        "Dream collaborations",
    ],
    "Travel ✈️": [
        "Journeys and discoveries",
        "Culture shocks and perspective shifts",
        "Planning quirks and travel style",
        "Travel buddies and group dynamics",
        "Memorable moments from trips",
        "Lessons that stayed with you",
    ],
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
    max_score: int = 100
    language: str = "en"
    llm_model: str = "gemini-2.5-flash"

    def to_dict(self) -> Dict[str, object]:
        return {
            "max_score": self.max_score,
            "language": self.language,
            "llm_model": self.llm_model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "RoomSettings":
        return cls(
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
