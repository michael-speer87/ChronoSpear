from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cam_native_provider import ProviderResult


@dataclass(frozen=True)
class LlamaCppToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LlamaCppToolResult:
    content: str | None
    tool_calls: tuple[LlamaCppToolCall, ...]
    usage: dict[str, object]
    raw_assistant_message: dict[str, object]
    tool_calls_present: bool


@dataclass
class LlamaCppCamNativeProvider:
    """OpenAI-compatible provider for a persistent local llama.cpp server."""

    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "cam-native-v1"
    max_new_tokens: int = 192
    timeout_seconds: float = 120.0
    repetition_penalty: float = 1.05

    def __call__(self, messages: list[dict[str, str]]) -> ProviderResult:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_new_tokens,
            "temperature": 0.0,
            "stream": False,
            "repeat_penalty": self.repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        start = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"llama.cpp server returned HTTP {exc.code}{suffix}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach llama.cpp server at {self.base_url}: {exc.reason}"
            ) from exc
        elapsed = perf_counter() - start

        try:
            body = json.loads(raw)
            choice = body["choices"][0]
            message = choice["message"]
            text = message.get("content") or ""
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected llama.cpp response payload: {raw[:500]}") from exc

        text = str(text).strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()

        raw_usage = body.get("usage", {})
        usage: dict[str, object] = dict(raw_usage) if isinstance(raw_usage, dict) else {}
        usage["total_time"] = elapsed

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if (
            "total_tokens" not in usage
            and isinstance(prompt_tokens, int)
            and isinstance(completion_tokens, int)
        ):
            usage["total_tokens"] = prompt_tokens + completion_tokens

        return ProviderResult(text=text, usage=usage)


@dataclass
class LlamaCppToolProvider:
    """OpenAI-compatible llama.cpp provider requiring structural tool calls."""

    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "cam-native-v1"
    max_new_tokens: int = 192
    timeout_seconds: float = 120.0
    repetition_penalty: float = 1.05
    tool_choice: str = "auto"

    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> LlamaCppToolResult:
        if self.tool_choice not in {"auto", "required"}:
            raise ValueError("tool_choice must be 'auto' or 'required'")
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": list(tools),
            "tool_choice": self.tool_choice,
            "max_tokens": self.max_new_tokens,
            "temperature": 0.0,
            "stream": False,
            "repeat_penalty": self.repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        started = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(
                f"llama.cpp server returned HTTP {exc.code}{suffix}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach llama.cpp server at {self.base_url}: {exc.reason}"
            ) from exc

        try:
            body = json.loads(raw)
            message = body["choices"][0]["message"]
            calls = tuple(
                LlamaCppToolCall(
                    call_id=item["id"],
                    name=item["function"]["name"],
                    arguments=item["function"]["arguments"],
                )
                for item in message.get("tool_calls", ())
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected llama.cpp tool response payload: {raw[:500]}"
            ) from exc

        raw_usage = body.get("usage", {})
        usage: dict[str, object] = (
            dict(raw_usage) if isinstance(raw_usage, dict) else {}
        )
        usage["total_time"] = perf_counter() - started
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if (
            "total_tokens" not in usage
            and isinstance(prompt_tokens, int)
            and isinstance(completion_tokens, int)
        ):
            usage["total_tokens"] = prompt_tokens + completion_tokens
        content = message.get("content")
        raw_assistant_message: dict[str, object] = {"content": content}
        if "tool_calls" in message:
            raw_assistant_message["tool_calls"] = message["tool_calls"]
        return LlamaCppToolResult(
            content=content if isinstance(content, str) else None,
            tool_calls=calls,
            usage=usage,
            raw_assistant_message=raw_assistant_message,
            tool_calls_present="tool_calls" in message,
        )
