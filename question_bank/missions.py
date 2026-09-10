"""Bounded, advisory missions; never question-admission requirements."""

from __future__ import annotations

from question_bank.semantic import normalize_question

DIMENSIONS = ("aspect", "scenario", "perspective", "contrast")


def mission_schema() -> dict:
    fields = {
        "agent_slot": {"type": "integer", "enum": [0, 1, 2, 3]},
        "level": {"type": "string", "enum": ["shallow", "deep"]},
        "brief": {"type": "string", "minLength": 1, "maxLength": 400},
        **{name: {"type": ["string", "null"], "minLength": 1, "maxLength": 120} for name in DIMENSIONS},
        "theme_hints": {"type": "array", "maxItems": 3, "items": {"type": "string", "minLength": 1, "maxLength": 80}},
    }
    return {"type": "array", "minItems": 4, "maxItems": 4, "items": {
        "type": "object", "properties": fields, "required": list(fields), "additionalProperties": False,
    }}


def validate_missions(value: object, levels: tuple[str, ...] = ("shallow", "deep")) -> list[dict]:
    """Validate structure and slot/Level consistency, not creative merit."""
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("exactly four next missions are required")
    slots = set()
    briefs = set()
    fields = {"agent_slot", "level", "brief", "theme_hints", *DIMENSIONS}
    for mission in value:
        if not isinstance(mission, dict) or set(mission) != fields:
            raise ValueError("invalid mission fields")
        slot = mission["agent_slot"]
        if type(slot) is not int or slot not in range(4) or slot in slots:
            raise ValueError("mission slots must be unique integers 0–3")
        slots.add(slot)
        if mission["level"] != slot_level(slot, levels):
            raise ValueError("mission Level does not match the campaign slot")
        brief = mission["brief"]
        if not isinstance(brief, str) or not 1 <= len(brief.strip()) <= 400 or len(brief) > 400:
            raise ValueError("invalid mission brief")
        normalized = normalize_question(brief)
        if not normalized or normalized in briefs:
            raise ValueError("mission briefs must be distinct")
        briefs.add(normalized)
        for name in DIMENSIONS:
            hint = mission[name]
            if hint is not None and (not isinstance(hint, str) or not hint.strip() or len(hint) > 120):
                raise ValueError("invalid optional mission dimension")
        themes = mission["theme_hints"]
        if not isinstance(themes, list) or len(themes) > 3 or any(
            not isinstance(theme, str) or not theme.strip() or len(theme) > 80 or theme.casefold() == "random"
            for theme in themes
        ):
            raise ValueError("invalid optional theme hints")
    return sorted(value, key=lambda mission: mission["agent_slot"])


def slot_level(slot: int, levels: tuple[str, ...]) -> str:
    if levels not in (("shallow",), ("deep",), ("shallow", "deep")):
        raise ValueError("invalid campaign levels")
    return levels[0] if len(levels) == 1 else levels[slot // 2]


def missions_from_advice(advice: dict | None, levels: tuple[str, ...] = ("shallow", "deep")) -> list[dict] | None:
    try:
        return validate_missions(advice.get("next_missions"), levels) if isinstance(advice, dict) else None
    except ValueError:
        return None
