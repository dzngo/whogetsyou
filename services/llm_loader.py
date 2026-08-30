import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from openai import OpenAI

from models import resolve_llm_model


def _content_to_text(content: Any) -> str:
    """Normalize message content fragments into a single text string."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if text_value:
                    pieces.append(str(text_value))
            elif item:
                pieces.append(str(item))
        return "\n".join(piece for piece in pieces if piece)
    if content is None:
        return ""
    return str(content)


def _completion_to_text(completion: Any) -> str:
    """Extract concatenated text from a chat completion response."""

    text = getattr(completion, "output_text", None)
    if text:
        if isinstance(text, list):
            text = "\n".join(str(part).strip() for part in text if str(part).strip())
        if isinstance(text, str):
            text = text.strip()
            if text:
                return text
    fragments: List[str] = []
    for choice in getattr(completion, "choices", []) or []:
        message = getattr(choice, "message", None)
        if message is None:
            continue
        fragments.append(_content_to_text(getattr(message, "content", "")))
    text = "\n".join(fragment.strip() for fragment in fragments if fragment and fragment.strip()).strip()
    if not text:
        raise RuntimeError("No text output returned by the LLM")
    return text


def _safe_structured_parse(completion: Any, response_model: Any):
    parsed = getattr(completion, "output_parsed", None)
    if parsed is not None:
        if isinstance(parsed, response_model):
            return parsed
        return response_model.model_validate(parsed)
    for choice in getattr(completion, "choices", []) or []:
        message = getattr(choice, "message", None)
        if message is None:
            continue
        parsed = getattr(message, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, response_model):
                return parsed
            return response_model.model_validate(parsed)
    # Fall back to validating from raw JSON content when no parsed payload is present.
    raw_text = _completion_to_text(completion)
    return response_model.model_validate_json(raw_text)


class BaseLLM(ABC):
    """Abstract base interface for LLM wrappers."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.timeout_seconds = 60
        self.last_response_metadata: Dict[str, Any] = {}

    def _capture_metadata(self, completion: Any) -> None:
        self.last_response_metadata = {
            key: value
            for key, value in {
                "response_id": getattr(completion, "id", None),
                "reported_model": getattr(completion, "model", None),
                "system_fingerprint": getattr(completion, "system_fingerprint", None),
            }.items()
            if value is not None
        }

    @abstractmethod
    def parse_structured(self, messages: Sequence[Dict[str, str]], response_model: Any) -> Any:
        """Return a structured response parsed into the provided Pydantic model."""

    @abstractmethod
    def complete_text(self, messages: Sequence[Dict[str, str]]) -> str:
        """Return plain-text completion output for the conversation."""


class GeminiLLM(BaseLLM):
    """LLM wrapper that routes Gemini models through the OpenAI compatibility API."""

    def __init__(self, model: str, api_key: str, base_url: str, reasoning_effort: Optional[str] = None):
        super().__init__(model)
        # AgentRunner owns the single permitted execution retry. Disable SDK
        # retries so the audited attempt count is the real provider call count.
        self._client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=60.0, max_retries=0
        )
        self._reasoning_effort = reasoning_effort

    def parse_structured(self, messages: Sequence[Dict[str, str]], response_model: Any) -> Any:
        request_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": list(messages),
            "response_format": response_model,
        }
        if self._reasoning_effort:
            request_kwargs["reasoning_effort"] = self._reasoning_effort
        completion = self._client.beta.chat.completions.parse(**request_kwargs)
        self._capture_metadata(completion)
        return _safe_structured_parse(completion, response_model)

    def complete_text(self, messages: Sequence[Dict[str, str]]) -> str:
        request_kwargs: Dict[str, Any] = {"model": self.model_name, "messages": list(messages)}
        if self._reasoning_effort:
            request_kwargs["reasoning_effort"] = self._reasoning_effort
        completion = self._client.chat.completions.create(**request_kwargs)
        self._capture_metadata(completion)
        return _completion_to_text(completion)


class OpenAILLM(BaseLLM):
    """LLM wrapper for native OpenAI chat models."""

    def __init__(self, model: str, api_key: str, reasoning_effort: Optional[str] = None):
        super().__init__(model)
        self._client = OpenAI(api_key=api_key, timeout=60.0, max_retries=0)
        self._reasoning_effort = reasoning_effort

    def parse_structured(self, messages: Sequence[Dict[str, str]], response_model: Any) -> Any:
        request_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "input": list(messages),
            "text_format": response_model,
        }
        if self._reasoning_effort:
            request_kwargs["reasoning"] = {"effort": self._reasoning_effort}
        completion = self._client.responses.parse(**request_kwargs)
        self._capture_metadata(completion)
        return _safe_structured_parse(completion, response_model)

    def complete_text(self, messages: Sequence[Dict[str, str]]) -> str:
        request_kwargs: Dict[str, Any] = {"model": self.model_name, "messages": list(messages)}
        if self._reasoning_effort:
            request_kwargs["reasoning_effort"] = self._reasoning_effort
        completion = self._client.chat.completions.create(**request_kwargs)
        self._capture_metadata(completion)
        return _completion_to_text(completion)


def _get_secret(name: str) -> Optional[str]:
    """Return a credential from env vars or Streamlit secrets when available."""
    value = os.getenv(name)
    if not value:
        load_dotenv()
        value = os.getenv(name)
    if value:
        return value
    import streamlit as st  # type: ignore

    if name in st.secrets:
        return str(st.secrets[name])

    return None


def get_llm(model_name: Optional[str] = None) -> BaseLLM:
    """Instantiate the appropriate LLM wrapper based on the requested model."""
    if model_name is None:
        model_name = "gemini-2.5-flash"  # default model

    selection_key = model_name.lower()
    config = resolve_llm_model(selection_key)
    provider_model = config.provider_model
    reasoning_effort = config.reasoning_effort

    if config.provider == "gemini":
        api_key = _get_secret("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(f"GOOGLE_API_KEY  must be set to use {model_name} models")

        return GeminiLLM(
            model=provider_model,
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            reasoning_effort=reasoning_effort,
        )
    if config.provider == "openai":
        api_key = _get_secret("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(f"OPENAI_API_KEY must be set to use {model_name} models")
        return OpenAILLM(model=provider_model, api_key=api_key, reasoning_effort=reasoning_effort)

    raise NotImplementedError(f"Provider '{config.provider}' is not supported")
