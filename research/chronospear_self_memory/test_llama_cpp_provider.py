from __future__ import annotations

import json
from urllib.error import URLError

import llama_cpp_provider as provider_module
import pytest
from llama_cpp_provider import LlamaCppCamNativeProvider, LlamaCppToolProvider


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


@pytest.mark.parametrize("tool_choice", ["auto", "required"])
def test_llama_cpp_tool_provider_sends_and_parses_native_tool_messages(
    monkeypatch,
    tool_choice,
) -> None:
    captured_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "history-1",
                            "type": "function",
                            "function": {
                                "name": "get_history",
                                "arguments": '{"name":"Alric"}',
                            },
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "answer-1",
                            "type": "function",
                            "function": {
                                "name": "submit_answer",
                                "arguments": '{"answer":"North Gate","evidence_ids":["HO-1"]}',
                            },
                        }],
                    }
                }],
                "usage": {},
            },
        ]
    )

    def fake_urlopen(request, timeout):
        assert timeout == 7.5
        captured_bodies.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(next(responses))

    monkeypatch.setattr(provider_module, "urlopen", fake_urlopen)
    tools = (
        {"type": "function", "function": {"name": "get_history"}},
        {"type": "function", "function": {"name": "submit_answer"}},
    )
    provider = LlamaCppToolProvider(
        timeout_seconds=7.5,
        tool_choice=tool_choice,
    )
    messages: list[dict[str, object]] = [
        {"role": "system", "content": "contract"},
        {"role": "user", "content": "opening packet"},
    ]

    history = provider(messages, tools)
    messages.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "history-1",
                    "type": "function",
                    "function": {
                        "name": "get_history",
                        "arguments": '{"name":"Alric"}',
                    },
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "history-1",
                "name": "get_history",
                "content": "admitted History delta",
            },
        ]
    )
    answer = provider(messages, tools)

    assert captured_bodies[0]["tools"] == list(tools)
    assert captured_bodies[1]["tools"] == list(tools)
    assert captured_bodies[1]["messages"] == messages
    assert captured_bodies[0]["tool_choice"] == tool_choice
    assert captured_bodies[1]["tool_choice"] == tool_choice
    assert history.tool_calls[0].name == "get_history"
    assert history.tool_calls[0].arguments == '{"name":"Alric"}'
    assert history.tool_calls_present is True
    assert history.raw_assistant_message["tool_calls"]
    assert history.usage["total_tokens"] == 13
    assert answer.tool_calls[0].name == "submit_answer"
