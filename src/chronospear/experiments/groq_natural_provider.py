from __future__ import annotations

import os
from collections.abc import Mapping

from chronospear.experiments.groq_provider import (
    GroqProviderError,
    Transport,
    _default_transport,
)
from chronospear.experiments.natural_language_cam import (
    NaturalLanguageProviderRequest,
    NaturalLanguageProviderResponse,
)

_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "openai/gpt-oss-20b"

NATURAL_LANGUAGE_SYSTEM_PROMPT = (
    "You are a bounded-evidence reasoning experiment. Use only the supplied CAM "
    "evidence. If the evidence is sufficient, respond only with a compact natural-language "
    "conclusion. If the evidence is insufficient, respond only with a natural-language "
    "request describing the additional world information you need. Ask only in ordinary "
    "language and do not mention implementation details."
)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise GroqProviderError(f"Groq response {label} must be an object.")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GroqProviderError(f"Groq response {label} must be a non-negative integer.")
    return value


def _optional_float(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise GroqProviderError(f"Groq response {label} must be non-negative.")
    return float(value)


class GroqNaturalLanguageProvider:
    """Plain-text Groq adapter for natural-language expansion experiments only."""

    __slots__ = ("_api_key", "_model", "_timeout_seconds", "_transport")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 30,
        transport: Transport = _default_transport,
    ) -> None:
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise GroqProviderError("GROQ_API_KEY is required for the live experiment.")
        self._api_key = key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def __call__(
        self, request: NaturalLanguageProviderRequest
    ) -> NaturalLanguageProviderResponse:
        messages: list[Mapping[str, str]] = [
            {"role": "system", "content": NATURAL_LANGUAGE_SYSTEM_PROMPT}
        ]
        messages.extend(
            {"role": message.role, "content": message.content}
            for message in request.messages
        )
        payload: Mapping[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
            "seed": 7,
            "max_completion_tokens": 180,
        }
        body, wall_latency = self._transport(
            _CHAT_COMPLETIONS_URL,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChronoSpear-CAM-Experiment/0.1",
            },
            payload,
            self._timeout_seconds,
        )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GroqProviderError("Groq response choices must be a non-empty array.")
        choice = _mapping(choices[0], "choice")
        message = _mapping(choice.get("message"), "message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise GroqProviderError(
                "Groq response content must be non-empty text.",
                wall_latency_seconds=wall_latency,
                response_body=body,
            )
        usage = _mapping(body.get("usage"), "usage")
        model = body.get("model")
        if not isinstance(model, str):
            raise GroqProviderError("Groq response model must be text.")
        return NaturalLanguageProviderResponse(
            raw_text=content,
            input_tokens=_integer(usage.get("prompt_tokens"), "prompt_tokens"),
            output_tokens=_integer(usage.get("completion_tokens"), "completion_tokens"),
            model=model,
            provider_latency_seconds=_optional_float(usage.get("total_time"), "total_time"),
            wall_latency_seconds=wall_latency,
        )
