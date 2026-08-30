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


@dataclass(frozen=True)
class QuestionAngle:
    key: str
    guidance: str
    weight: float = 1.0


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
    "Random 🎲",
]

THEME_DESCRIPTIONS: Dict[str, List[str]] = {
    "Yourself 🌱": [
        "Self-awareness and identity shifts",
        "Snapshots from your personal daily life",
        "Facts about you and your interests",
        "How you understand yourself",
        "Self-talk and inner dialogue",
        "Micro-habits that reveal who you are",
        "How your thoughts, emotions, and behaviors align with your values",
        "How other people perceive you versus how you see yourself",
        "Emotional triggers and how you regulate them",
        "Strengths, blind spots, and patterns you keep noticing",
        "Decisions that changed your sense of purpose or direction",
    ],
    "Childhood 👶": [
        "Memories and stories from your early years",
        "Lessons from your upbringing",
        "Family dynamics when you were growing up",
        "Formative childhood friendships",
        "Caretakers and their impact on you",
        "Big feelings from kid years",
        "Moments when you felt especially safe, protected, or understood",
        "Positive childhood experiences that still shape your relationships",
        "Community traditions and places that made you feel you belonged",
        "Play, imagination, and the worlds you created as a child",
        "Early experiences that changed how you handle fear, trust, or confidence",
    ],
    "Family 🏡": [
        "Experiences with family members",
        "Warm and messy family moments",
        "Traditions and rituals at home",
        "Conflict and repair in family life",
        "Generational expectations and boundaries",
        "Quirks that define your home life",
        "Everyday routines that made home feel stable or chaotic",
        "Roles you naturally take on in your family",
        "Ways your family shows care, loyalty, or protection",
        "Conversations, tensions, or values that repeat across generations",
        "How you balance closeness with independence in family relationships",
    ],
    "Goals ✨": [
        "Dreams you are actively pursuing",
        "Milestones you want to reach",
        "Career leaps you are aiming for",
        "Health goals and personal growth quests",
        "Creative ambitions",
        "Bucket-list experiments",
        "Goals that feel deeply connected to your values",
        "How you stay motivated when progress is slow",
        "Habits and systems that move you forward",
        "Setbacks, pivots, and how you redefine success",
        "How you measure progress and hold yourself accountable",
    ],
    "Work 💼": [
        "How you show up professionally",
        "Coworker and manager relationships",
        "Team dynamics and collaboration",
        "Challenges and pressure at work",
        "Leadership style and growth",
        "Promotion or burnout recovery stories",
        "Psychological safety and what helps you speak up",
        "How you handle competing priorities and role conflict",
        "What energizes you versus what drains you at work",
        "How you build trust, clarity, and momentum on a team",
        "How leadership pressure changes your day-to-day emotions",
    ],
    "Love 💖": [
        "Romantic relationships and intimacy",
        "How you show love to a partner",
        "Dating history and patterns",
        "Love languages and communication styles",
        "Conflict repair in relationships",
        "What you want next in love",
        "How trust is built or broken in small everyday moments",
        "Boundaries that help you feel safe and close",
        "Emotional, intellectual, physical, or experiential intimacy",
        "How you reconnect after hurt, distance, or misunderstanding",
        "Needs or desires that are hard for you to say out loud",
    ],
    "Friends 🤝": [
        "Friendship stories old and new",
        "Chosen-family moments",
        "How you support and are supported",
        "Inside jokes and shared rituals",
        "Boundaries and loyalty in friendships",
        "Long-distance friendship dynamics",
        "The friendships that make you feel most like yourself",
        "Quality versus quantity in your social life",
        "Meaningful conversations that made you feel more connected",
        "How you maintain friendship during busy or changing life stages",
        "When reaching out, being reached for, or being remembered mattered",
    ],
    "Hobbies 🎨": [
        "Passions and creative outlets",
        "How you unwind and recharge",
        "Learning curves in your craft",
        "Communities around your hobbies",
        "Resources you lean on to improve",
        "Dream collaborations",
        "How hobbies shape your identity outside work or responsibility",
        "Play, curiosity, and experimentation for their own sake",
        "The discipline, patience, or confidence a hobby builds in you",
        "How leisure affects your mood, resilience, or mental clarity",
        "Social connection, belonging, or mentorship through a hobby community",
    ],
    "Travel ✈️": [
        "Journeys and discoveries",
        "Culture shocks and perspective shifts",
        "Planning quirks and travel style",
        "Travel buddies and group dynamics",
        "Memorable moments from trips",
        "Lessons that stayed with you",
        "Travel experiences that challenged your assumptions",
        "Curiosity, openness, and how you engage with difference",
        "Conversations with locals that changed how you saw a place",
        "Moments when travel made you more aware of inequality or privilege",
        "The difference between just visiting and truly paying attention",
    ],
    "Random 🎲": [
        "Randomness",
    ],
}

GENERIC_QUESTION_ANGLES: Dict[str, List[QuestionAngle]] = {
    Level.SHALLOW.value: [
        QuestionAngle("everyday_preference", "Ask about one realistic everyday preference connected to the selected theme."),
        QuestionAngle("small_routine", "Ask about one small routine or habit connected to the selected theme."),
        QuestionAngle("simple_choice", "Ask about one light choice the player would plausibly make in real life."),
        QuestionAngle("communication_style", "Ask about one simple communication or social style connected to the selected theme."),
        QuestionAngle("plausible_situation", "Ask what the player would do in one plausible everyday situation connected to the selected theme."),
        QuestionAngle("small_joy", "Ask about one small thing the player enjoys, notices, or looks forward to."),
    ],
    Level.DEEP.value: [
        QuestionAngle("values", "Ask about one value or principle connected to the selected theme."),
        QuestionAngle("memory", "Ask about one specific memory connected to the selected theme."),
        QuestionAngle("relationship_pattern", "Ask about one relationship pattern or way of showing up connected to the selected theme."),
        QuestionAngle("growth", "Ask about one personal growth moment connected to the selected theme."),
        QuestionAngle("belief", "Ask about one belief, assumption, or perspective connected to the selected theme."),
        QuestionAngle("hope", "Ask about one hope, fear, or future-facing reflection connected to the selected theme."),
    ],
}

QUESTION_ANGLES: Dict[str, Dict[str, List[QuestionAngle]]] = {
    "Yourself 🌱": {
        Level.SHALLOW.value: [
            QuestionAngle("free_time", "Ask what the player likes doing during free time or a relaxed day."),
            QuestionAngle("music_media", "Ask about music, movies, shows, books, or online content the player usually enjoys."),
            QuestionAngle("food_drink", "Ask about one everyday food or drink preference.", weight=0.6),
            QuestionAngle("small_joy", "Ask about one small thing that makes the player's day better."),
            QuestionAngle("season_weather", "Ask about the player's favorite season, weather, or outdoor feeling."),
            QuestionAngle("planning_style", "Ask whether the player prefers planning ahead or being spontaneous."),
            QuestionAngle("communication_style", "Ask about texting, calling, replying, or talking in person."),
            QuestionAngle("tidiness_style", "Ask about being tidy, flexible, organized, or naturally casual."),
            QuestionAngle("hobbies", "Ask about a hobby the player has or wants to try."),
            QuestionAngle("small_strength", "Ask about one simple thing the player thinks they are good at."),
            QuestionAngle("favorite_place", "Ask about a place where the player likes spending time."),
            QuestionAngle("first_impression", "Ask what others may notice first about the player."),
        ],
        Level.DEEP.value: [
            QuestionAngle("identity", "Ask about how the player understands who they are becoming."),
            QuestionAngle("self_perception", "Ask about the gap between how the player sees themself and how others see them."),
            QuestionAngle("values", "Ask about a value that quietly guides the player's choices."),
            QuestionAngle("emotional_pattern", "Ask about a recurring emotional pattern the player has noticed."),
            QuestionAngle("growth", "Ask about a personal change that shaped how the player sees themself."),
            QuestionAngle("inner_dialogue", "Ask about the player's self-talk or private inner standards."),
            QuestionAngle("blind_spot", "Ask about a blind spot or recurring pattern the player is learning from."),
            QuestionAngle("purpose", "Ask about a decision that changed the player's sense of direction."),
        ],
    },
    "Childhood 👶": {
        Level.SHALLOW.value: [
            QuestionAngle("favorite_game", "Ask about a childhood game or activity the player enjoyed."),
            QuestionAngle("school_day", "Ask about one simple school-day preference or routine."),
            QuestionAngle("childhood_snack", "Ask about one childhood snack or treat.", weight=0.6),
            QuestionAngle("cartoon_show", "Ask about a childhood show, book, song, or toy the player liked."),
            QuestionAngle("play_place", "Ask about a place where the player liked to play or spend time."),
            QuestionAngle("small_rule", "Ask about one harmless childhood rule, habit, or routine."),
            QuestionAngle("weekend_activity", "Ask about what the player liked doing on weekends as a child."),
            QuestionAngle("kid_preference", "Ask about one simple preference the player had as a child."),
        ],
        Level.DEEP.value: [
            QuestionAngle("safe_memory", "Ask about a childhood moment when the player felt safe or understood."),
            QuestionAngle("upbringing_lesson", "Ask about one lesson from the player's upbringing."),
            QuestionAngle("early_friendship", "Ask about a childhood friendship that shaped the player."),
            QuestionAngle("family_dynamic", "Ask about one family dynamic from growing up."),
            QuestionAngle("belonging", "Ask about a childhood place or tradition that created belonging."),
            QuestionAngle("fear_confidence", "Ask about an early experience that shaped fear, trust, or confidence."),
            QuestionAngle("caretaker_impact", "Ask about how a caretaker influenced the player."),
            QuestionAngle("imagination", "Ask about how childhood imagination still affects the player."),
        ],
    },
    "Family 🏡": {
        Level.SHALLOW.value: [
            QuestionAngle("home_routine", "Ask about one ordinary home or family routine."),
            QuestionAngle("family_meal", "Ask about a light family meal or dinner-table preference.", weight=0.6),
            QuestionAngle("chores", "Ask about one chore or home task style."),
            QuestionAngle("family_role", "Ask about the player's light role in family situations."),
            QuestionAngle("weekend_home", "Ask about a family weekend or at-home preference."),
            QuestionAngle("care_gesture", "Ask about one small way family members show care."),
            QuestionAngle("shared_space", "Ask about a favorite shared space or home habit."),
            QuestionAngle("family_ritual", "Ask about a simple ritual, tradition, or repeated family moment."),
        ],
        Level.DEEP.value: [
            QuestionAngle("family_role", "Ask about the role the player naturally takes in family life."),
            QuestionAngle("boundaries", "Ask about balancing closeness and independence in family relationships."),
            QuestionAngle("generational_values", "Ask about a value or expectation passed through the family."),
            QuestionAngle("care_language", "Ask about how the player's family tends to show care."),
            QuestionAngle("conflict_repair", "Ask about how repair happens after family conflict."),
            QuestionAngle("home_stability", "Ask about what made home feel stable or chaotic."),
            QuestionAngle("loyalty", "Ask about family loyalty, protection, or responsibility."),
            QuestionAngle("repeated_conversation", "Ask about a family conversation or tension that repeats across time."),
        ],
    },
    "Goals ✨": {
        Level.SHALLOW.value: [
            QuestionAngle("small_goal", "Ask about one small goal or achievement the player would enjoy."),
            QuestionAngle("skill_to_try", "Ask about a skill, class, or hobby the player wants to try."),
            QuestionAngle("planning_style", "Ask about how the player likes planning or tracking goals."),
            QuestionAngle("motivation_routine", "Ask about one light routine that helps the player get started."),
            QuestionAngle("bucket_activity", "Ask about one realistic activity or experience the player looks forward to."),
            QuestionAngle("progress_reward", "Ask about a small reward the player likes after making progress."),
            QuestionAngle("energy_time", "Ask what time, place, or condition helps the player work on goals."),
            QuestionAngle("low_pressure_ambition", "Ask about a low-pressure ambition that would still feel satisfying."),
        ],
        Level.DEEP.value: [
            QuestionAngle("values", "Ask about a goal connected to the player's values."),
            QuestionAngle("motivation", "Ask about what keeps the player motivated when progress is slow."),
            QuestionAngle("setback", "Ask about a setback that changed how the player defines success."),
            QuestionAngle("accountability", "Ask about how the player holds themself accountable."),
            QuestionAngle("identity", "Ask about how a goal connects to who the player wants to become."),
            QuestionAngle("pivot", "Ask about a time the player changed direction on an important goal."),
            QuestionAngle("fear", "Ask about a fear or hesitation around pursuing a goal."),
            QuestionAngle("future_self", "Ask about what the player's future self would thank them for starting."),
        ],
    },
    "Work 💼": {
        Level.SHALLOW.value: [
            QuestionAngle("focus_style", "Ask about how the player likes to focus during work."),
            QuestionAngle("meeting_style", "Ask about one light meeting or collaboration preference."),
            QuestionAngle("break_habits", "Ask about a small break habit that helps the player reset."),
            QuestionAngle("workspace_preference", "Ask about desk, workspace, tool, or environment preferences."),
            QuestionAngle("communication_style", "Ask about work messages, updates, directness, or response style."),
            QuestionAngle("task_start", "Ask about how the player likes starting a work task."),
            QuestionAngle("team_role", "Ask about one light role the player tends to take in a team."),
            QuestionAngle("work_snack", "Ask about one work snack or drink preference.", weight=0.5),
        ],
        Level.DEEP.value: [
            QuestionAngle("motivation", "Ask about what energizes the player at work."),
            QuestionAngle("burnout", "Ask about what drains the player and how they recover."),
            QuestionAngle("leadership_pressure", "Ask about how responsibility changes the player's emotions or behavior."),
            QuestionAngle("trust", "Ask about what helps the player trust a team or manager."),
            QuestionAngle("speaking_up", "Ask about what helps the player speak up at work."),
            QuestionAngle("career_identity", "Ask about how work affects the player's sense of identity."),
            QuestionAngle("role_conflict", "Ask about handling competing priorities or expectations."),
            QuestionAngle("growth", "Ask about a work experience that changed the player's confidence."),
        ],
    },
    "Love 💖": {
        Level.SHALLOW.value: [
            QuestionAngle("date_preference", "Ask about one simple date or shared-time preference."),
            QuestionAngle("texting_style", "Ask about texting, replying, calling, or conversation style in dating."),
            QuestionAngle("small_gesture", "Ask about a small gesture that feels caring."),
            QuestionAngle("quality_time", "Ask about how the player likes spending relaxed time with someone."),
            QuestionAngle("planning_style", "Ask about planning dates, surprises, or spontaneous plans."),
            QuestionAngle("comfort_activity", "Ask about a realistic comfort activity in a relationship."),
            QuestionAngle("affection_style", "Ask about one light way the player shows affection."),
            QuestionAngle("shared_food", "Ask about a simple food or drink preference on a date.", weight=0.5),
        ],
        Level.DEEP.value: [
            QuestionAngle("trust", "Ask about how trust is built or broken in small moments."),
            QuestionAngle("boundaries", "Ask about a boundary that helps the player feel safe and close."),
            QuestionAngle("communication", "Ask about what kind of communication helps the player feel understood."),
            QuestionAngle("repair", "Ask about reconnecting after hurt or misunderstanding."),
            QuestionAngle("needs", "Ask about a need that is hard for the player to say out loud."),
            QuestionAngle("intimacy", "Ask about emotional, intellectual, or experiential intimacy."),
            QuestionAngle("pattern", "Ask about a relationship pattern the player has noticed."),
            QuestionAngle("future_love", "Ask about what the player hopes to build in love."),
        ],
    },
    "Friends 🤝": {
        Level.SHALLOW.value: [
            QuestionAngle("hangout_style", "Ask about how the player likes spending time with friends."),
            QuestionAngle("group_chat", "Ask about group chat habits, replies, or message style."),
            QuestionAngle("friend_role", "Ask about one light role the player tends to have in a friend group."),
            QuestionAngle("party_preference", "Ask about a realistic social gathering preference."),
            QuestionAngle("checking_in", "Ask about simple ways the player likes checking in with friends."),
            QuestionAngle("shared_activity", "Ask about one activity the player enjoys doing with friends."),
            QuestionAngle("inside_joke", "Ask about light inside-joke or shared ritual energy."),
            QuestionAngle("snack_drink", "Ask about a snack or drink preference when hanging out.", weight=0.5),
        ],
        Level.DEEP.value: [
            QuestionAngle("support", "Ask about how the player supports friends or receives support."),
            QuestionAngle("belonging", "Ask about friendships that make the player feel like themself."),
            QuestionAngle("loyalty", "Ask about what loyalty means to the player in friendship."),
            QuestionAngle("boundaries", "Ask about a friendship boundary the player values."),
            QuestionAngle("distance", "Ask about maintaining friendship through distance or busy seasons."),
            QuestionAngle("meaningful_conversation", "Ask about a conversation that made the player feel connected."),
            QuestionAngle("chosen_family", "Ask about chosen-family feelings in friendship."),
            QuestionAngle("being_remembered", "Ask about a time being remembered or reached for mattered."),
        ],
    },
    "Hobbies 🎨": {
        Level.SHALLOW.value: [
            QuestionAngle("favorite_hobby", "Ask about a hobby or interest the player enjoys."),
            QuestionAngle("hobby_to_try", "Ask about a hobby the player wants to try."),
            QuestionAngle("relaxation", "Ask how the player likes relaxing or recharging."),
            QuestionAngle("creative_routine", "Ask about one small creative routine or habit."),
            QuestionAngle("learning_style", "Ask how the player likes learning something new."),
            QuestionAngle("tools_places", "Ask about a tool, place, or setup connected to hobbies."),
            QuestionAngle("social_hobby", "Ask about hobbies done alone versus with other people."),
            QuestionAngle("hobby_snack", "Ask about a snack or drink around hobby time.", weight=0.4),
        ],
        Level.DEEP.value: [
            QuestionAngle("identity", "Ask how a hobby shapes the player's identity outside responsibilities."),
            QuestionAngle("curiosity", "Ask about curiosity, play, or experimentation in the player's life."),
            QuestionAngle("discipline", "Ask about patience or discipline a hobby has taught the player."),
            QuestionAngle("confidence", "Ask about confidence built through a hobby."),
            QuestionAngle("mental_clarity", "Ask how leisure affects the player's mood or mental clarity."),
            QuestionAngle("belonging", "Ask about belonging or mentorship through a hobby community."),
            QuestionAngle("creative_growth", "Ask about creative growth or a learning curve."),
            QuestionAngle("purpose", "Ask why a hobby matters beyond productivity."),
        ],
    },
    "Travel ✈️": {
        Level.SHALLOW.value: [
            QuestionAngle("travel_style", "Ask whether the player prefers planned, relaxed, fast, or spontaneous travel."),
            QuestionAngle("free_day", "Ask how the player likes spending a free day in a new place."),
            QuestionAngle("packing_habit", "Ask about packing habits or comfort items."),
            QuestionAngle("weather_place", "Ask about travel weather, scenery, or place preferences."),
            QuestionAngle("trip_activity", "Ask about one activity the player likes doing while traveling."),
            QuestionAngle("travel_buddy", "Ask about light group-trip roles or travel buddy preferences."),
            QuestionAngle("airport_waiting", "Ask about what the player does while waiting during travel."),
            QuestionAngle("travel_food", "Ask about one food or drink preference while traveling.", weight=0.5),
        ],
        Level.DEEP.value: [
            QuestionAngle("perspective_shift", "Ask about a trip that changed the player's perspective."),
            QuestionAngle("culture_shock", "Ask about a moment that challenged the player's assumptions."),
            QuestionAngle("openness", "Ask how travel affects the player's curiosity or openness."),
            QuestionAngle("local_conversation", "Ask about a conversation with someone local that stayed with the player."),
            QuestionAngle("privilege_awareness", "Ask about a travel moment that made the player more aware of inequality or privilege."),
            QuestionAngle("attention", "Ask about the difference between visiting and truly paying attention."),
            QuestionAngle("group_dynamic", "Ask about what travel reveals about the player in groups."),
            QuestionAngle("lesson", "Ask about a lesson from travel that stayed with the player."),
        ],
    },
    "Random 🎲": {
        Level.SHALLOW.value: [
            QuestionAngle("free_time", "Ask about what the player does with unexpected free time."),
            QuestionAngle("music_media", "Ask about music, shows, movies, books, or casual entertainment."),
            QuestionAngle("food_drink", "Ask about one everyday food or drink preference.", weight=0.45),
            QuestionAngle("communication_style", "Ask about texting, calling, replying, or talking in person."),
            QuestionAngle("planning_style", "Ask about planning ahead versus improvising."),
            QuestionAngle("weather_season", "Ask about weather, seasons, or the player's preferred atmosphere."),
            QuestionAngle("places", "Ask about places where the player likes spending time."),
            QuestionAngle("small_routine", "Ask about one small daily routine or habit."),
            QuestionAngle("social_preference", "Ask about quiet versus lively settings or social energy."),
            QuestionAngle("shopping_errands", "Ask about a realistic shopping, errand, or small-choice habit."),
            QuestionAngle("waiting_time", "Ask what the player does while waiting or between plans."),
            QuestionAngle("small_strength", "Ask about one simple thing the player is good at."),
        ],
        Level.DEEP.value: [
            QuestionAngle("values", "Ask about one value that quietly guides the player."),
            QuestionAngle("turning_point", "Ask about one turning point that changed the player's direction."),
            QuestionAngle("relationship_pattern", "Ask about one recurring relationship pattern."),
            QuestionAngle("self_understanding", "Ask about something the player has learned about themself."),
            QuestionAngle("regret", "Ask about a regret or near-miss that still teaches the player something."),
            QuestionAngle("hope", "Ask about a hope the player carries into the future."),
            QuestionAngle("belief_change", "Ask about a belief that softened or strengthened over time."),
            QuestionAngle("hidden_story", "Ask about a part of the player's story they rarely share."),
        ],
    },
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
    "gpt-5.4-nano": "OpenAI GPT-5.4 Nano",
    "gpt-5.4-nano-high": "OpenAI GPT-5.4 Nano (High reasoning)",
    "gpt-5.4-mini": "OpenAI GPT-5.4 Mini",
    "gpt-5.4-mini-high": "OpenAI GPT-5.4 Mini (High reasoning)",
    "gpt-5-mini": "OpenAI GPT-5 Mini",
    "gpt-5-nano": "OpenAI GPT-5 Nano",
    "gpt-4o-mini": "OpenAI GPT-4o Mini",
    "gpt-4.1-nano": "OpenAI GPT-4.1 Nano",
    "gpt-5-mini	": "OpenAI GPT-5 Mini",
    "gpt-4o": "OpenAI GPT-4o",
    "gpt-4.1-mini": "OpenAI GPT-4.1 Mini",
    "gpt-4.1": "OpenAI GPT-4.1",
}

SUPPORTED_GEMINI_LLM_MODELS: Dict[str, str] = {
    "gemini-3.7-flash": "Gemini 3.7 Flash",
    "gemini-3.6-flash-low": "Gemini 3.6 Flash (Low thinking)",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.5-flash-high": "Gemini 3.5 Flash (High thinking)",
    "gemini-3.5-flash-lite-minimal": "Gemini 3.5 Flash Lite (Minimal thinking)",
    "gemini-3.5-flash-lite-high": "Gemini 3.5 Flash Lite (High thinking)",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-3-flash-minimal": "Gemini 3 Flash Preview (Minimal thinking)",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
}
SUPPORTED_LLM_MODELS: Dict[str, str] = SUPPORTED_OPENAI_LLM_MODELS | SUPPORTED_GEMINI_LLM_MODELS


@dataclass(frozen=True)
class LLMModelConfig:
    """Resolve a selectable model preset into provider request settings."""

    provider: str
    provider_model: str
    reasoning_effort: Optional[str] = None


LLM_MODEL_CONFIGS: Dict[str, LLMModelConfig] = {
    "gemini-3.6-flash-low": LLMModelConfig("gemini", "gemini-3.6-flash", "low"),
    "gemini-3.5-flash-high": LLMModelConfig("gemini", "gemini-3.5-flash", "high"),
    "gemini-3.5-flash-lite-minimal": LLMModelConfig("gemini", "gemini-3.5-flash-lite", "minimal"),
    "gemini-3.5-flash-lite-high": LLMModelConfig("gemini", "gemini-3.5-flash-lite", "high"),
    "gemini-3-flash-minimal": LLMModelConfig("gemini", "gemini-3-flash-preview", "minimal"),
    # Pin the translation preset to no reasoning without adding another UI option.
    "gpt-5.4-nano": LLMModelConfig("openai", "gpt-5.4-nano", "none"),
    "gpt-5.4-nano-high": LLMModelConfig("openai", "gpt-5.4-nano", "high"),
    "gpt-5.4-mini": LLMModelConfig("openai", "gpt-5.4-mini", "none"),
    "gpt-5.4-mini-high": LLMModelConfig("openai", "gpt-5.4-mini", "high"),
}


def resolve_llm_model(model_name: str) -> LLMModelConfig:
    """Return the authoritative provider configuration for a selectable preset."""
    selection_key = model_name.lower()
    if selection_key in LLM_MODEL_CONFIGS:
        return LLM_MODEL_CONFIGS[selection_key]
    if selection_key in SUPPORTED_GEMINI_LLM_MODELS:
        return LLMModelConfig("gemini", selection_key)
    if selection_key in SUPPORTED_OPENAI_LLM_MODELS:
        return LLMModelConfig("openai", selection_key)
    raise NotImplementedError(f"Model '{model_name}' is not supported by the LLM registry")


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
    is_private: bool
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
            "is_private": self.is_private,
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
            is_private=bool(data.get("is_private", False)),
            host_id=data["host_id"],
            host_name=data.get("host_name", ""),
            created_at=_iso_to_datetime(data["created_at"]),
            updated_at=_iso_to_datetime(data["updated_at"]),
            started=bool(data.get("started", False)),
            players=[Player.from_dict(player_data) for player_data in data.get("players", [])],
            settings=RoomSettings.from_dict(data["settings"]),
            game_state=dict(data.get("game_state", {})),
        )
