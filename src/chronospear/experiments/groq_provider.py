from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from chronospear.experiments.cam_llm import ProviderRequest, ProviderResponse

JsonObject = Mapping[str, object]
Transport = Callable[
    [str, Mapping[str, str], Mapping[str, object], float],
    tuple[Mapping[str, object], float],
]

_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "openai/gpt-oss-20b"


class GroqProviderError(RuntimeError):
    """Raised when the isolated Groq experiment adapter cannot complete a call."""

    def __init__(
        self,
        message: str,
        *,
        wall_latency_seconds: float | None = None,
        response_body: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.wall_latency_seconds = wall_latency_seconds
        self.response_body = response_body


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


def _default_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    timeout_seconds: float,
) -> tuple[Mapping[str, object], float]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        wall_latency = time.perf_counter() - started
        detail = exc.read().decode("utf-8", errors="replace")
        raise GroqProviderError(
            f"Groq HTTP {exc.code}: {detail}",
            wall_latency_seconds=wall_latency,
        ) from exc
    except urllib.error.URLError as exc:
        wall_latency = time.perf_counter() - started
        raise GroqProviderError(
            f"Groq request failed: {exc.reason}",
            wall_latency_seconds=wall_latency,
        ) from exc
    wall_latency = time.perf_counter() - started
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise GroqProviderError("Groq returned invalid JSON.") from exc
    return _mapping(decoded, "body"), wall_latency


class GroqProvider:
    """Groq Chat Completions adapter for the isolated CAM experiment."""

    __slots__ = (
        "_api_key",
        "_expansion_selectors",
        "_model",
        "_timeout_seconds",
        "_transport",
    )

    def __init__(
        self,
        *,
        expansion_selectors: tuple[str, ...],
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 30,
        transport: Transport = _default_transport,
    ) -> None:
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise GroqProviderError("GROQ_API_KEY is required for the live experiment.")
        self._api_key = key
        self._expansion_selectors = expansion_selectors
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def model(self) -> str:
        return self._model

    def __call__(self, request: ProviderRequest) -> ProviderResponse:
        selector_lines = "\n".join(f"- {selector}" for selector in self._expansion_selectors)
        if not selector_lines:
            selector_lines = "(none)"
        evidence = "\n".join(request.evidence)
        system_prompt = (
            "You are a bounded-evidence reasoning experiment. Use only the supplied CAM "
            "evidence. Return exactly one JSON object and no other text. If you can answer, "
            'return {"kind":"conclusion","text":"a compact conclusion"}. If more evidence '
            'is needed, return {"kind":"expand","selectors":["an available selector"],'
            '"reason":"a compact reason"}. Request only listed selectors and never invent facts.'
        )
        user_prompt = (
            f"ACTION\n{request.action}\n\n"
            f"CAM EVIDENCE\n{evidence}\n\n"
            f"AVAILABLE EXPANSION SELECTORS\n{selector_lines}"
        )
        payload: Mapping[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
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
        return self._parse_response(body, wall_latency)

    def _parse_response(
        self, body: Mapping[str, object], wall_latency: float
    ) -> ProviderResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GroqProviderError("Groq response choices must be a non-empty array.")
        choice = _mapping(choices[0], "choice")
        message = _mapping(choice.get("message"), "message")
        content = message.get("content")
        if not isinstance(content, str):
            raise GroqProviderError("Groq response content must be text.")
        try:
            protocol = _mapping(json.loads(content), "protocol content")
        except json.JSONDecodeError as exc:
            raise GroqProviderError("Groq protocol content was not valid JSON.") from exc

        usage = _mapping(body.get("usage"), "usage")
        input_tokens = _integer(usage.get("prompt_tokens"), "prompt_tokens")
        output_tokens = _integer(usage.get("completion_tokens"), "completion_tokens")
        provider_latency = _optional_float(usage.get("total_time"), "total_time")
        model = body.get("model")
        if not isinstance(model, str):
            raise GroqProviderError("Groq response model must be text.")

        kind = protocol.get("kind")
        if kind == "conclusion":
            text = protocol.get("text")
            if not isinstance(text, str):
                raise GroqProviderError("Groq conclusion text must be text.")
            return ProviderResponse(
                kind="conclusion",
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                provider_latency_seconds=provider_latency,
                wall_latency_seconds=wall_latency,
            )
        if kind == "expand":
            raw_selectors = protocol.get("selectors")
            reason = protocol.get("reason")
            if not isinstance(raw_selectors, list) or not all(
                isinstance(selector, str) for selector in raw_selectors
            ):
                raise GroqProviderError("Groq expansion selectors must be text strings.")
            if not isinstance(reason, str):
                raise GroqProviderError("Groq expansion reason must be text.")
            return ProviderResponse(
                kind="expand",
                selectors=tuple(raw_selectors),
                reason=reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                provider_latency_seconds=provider_latency,
                wall_latency_seconds=wall_latency,
            )
        raise GroqProviderError(f"Unknown Groq protocol response kind: {kind!r}.")
