from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cam_native_provider import ProviderResult


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
