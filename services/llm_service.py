"""Placeholder LLM service used for future enhancements."""

from __future__ import annotations

from typing import List

from models import DEFAULT_THEMES


class LLMService:
    """Thin abstraction over the eventual LLM integration."""

    def suggest_themes(self) -> List[str]:
        """Returns a list of starter themes."""
        return DEFAULT_THEMES.copy()
