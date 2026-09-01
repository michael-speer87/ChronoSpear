from __future__ import annotations

import json
from urllib.error import URLError

import pytest

import llama_cpp_provider as provider_module
from llama_cpp_provider import LlamaCppCamNativeProvider


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_llama_cpp_provider_uses_chat_endpoint_and_disables_thinking(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ANSWER: supported\nEVIDENCE: o-1",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )

    monkeypatch.setattr(provider_module, "urlopen", fake_urlopen)
    provider = LlamaCppCamNativeProvider(
        base_url="http://127.0.0.1:8080/v1/",
        model="cam-native-v1",
        timeout_seconds=7.5,
    )

    result = provider(
        [
            {"role": "system", "content": "contract"},
            {"role": "user", "content": "packet"},
        ]
    )

    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["timeout"] == 7.5
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "cam-native-v1"
    assert body["temperature"] == 0.0
    assert body["stream"] is False
    assert body["repeat_penalty"] == 1.05
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"][1]["content"] == "packet"
    assert result.text == "ANSWER: supported\nEVIDENCE: o-1"
    assert result.usage["prompt_tokens"] == 10
    assert result.usage["completion_tokens"] == 5
    assert result.usage["total_tokens"] == 15
    assert isinstance(result.usage["total_time"], float)


def test_llama_cpp_provider_strips_visible_thinking_wrapper(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "<think>hidden</think>\nANSWER: done\nEVIDENCE: none",
                        }
                    }
                ],
                "usage": {},
            }
        )

    monkeypatch.setattr(provider_module, "urlopen", fake_urlopen)
    result = LlamaCppCamNativeProvider()([{"role": "user", "content": "packet"}])
    assert result.text == "ANSWER: done\nEVIDENCE: none"


def test_llama_cpp_provider_reports_unreachable_server(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(provider_module, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Could not reach llama.cpp server"):
        LlamaCppCamNativeProvider()([{"role": "user", "content": "packet"}])
