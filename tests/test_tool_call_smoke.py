from __future__ import annotations

import importlib
import io
import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
smoke: Any = importlib.import_module("tool_call_smoke")


class FakeResponse:
    status = 200

    def __init__(self, message: dict[str, object]) -> None:
        self.message = message

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"choices": [{"message": self.message}]}).encode()


@pytest.mark.parametrize("mode", ["auto", "required"])
def test_smoke_sends_exact_echo_schema_and_requested_mode(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Any, *, timeout: int) -> FakeResponse:
        captured.update(json.loads(request.data.decode()))
        assert timeout == 120
        return FakeResponse(
            {
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"value":"potato"}',
                    },
                }],
            }
        )

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)
    result = smoke.run_smoke("http://127.0.0.1:8081/v1", "qwen3-base-v1", mode)

    assert captured["tool_choice"] == mode
    assert captured["tools"] == [smoke.ECHO_TOOL]
    assert captured["messages"] == [{"role": "user", "content": smoke.PROMPT}]
    assert result.tool_calls_present is True
    assert result.tool_calls[0]["function"] == {
        "name": "echo",
        "arguments": '{"value":"potato"}',
    }


def test_ordinary_content_is_not_treated_as_a_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_json = '{"name":"echo","arguments":{"value":"potato"}}'
    monkeypatch.setattr(
        smoke.urllib.request,
        "urlopen",
        lambda _request, timeout: FakeResponse({"content": fake_json}),
    )

    result = smoke.run_smoke("http://127.0.0.1:8081/v1", "qwen3-base-v1", "auto")

    assert result.content == fake_json
    assert result.tool_calls is None
    assert result.tool_calls_present is False


def test_http_diagnostic_exposes_body_without_api_keys_or_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = b'{"error":{"message":"required is unsupported"}}'

    def fail(request: Any, *, timeout: int) -> Any:
        assert "Authorization" not in dict(request.header_items())
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            Message(),
            io.BytesIO(response_body),
        )

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fail)
    result = smoke.run_smoke(
        "http://127.0.0.1:8081/v1", "qwen3-base-v1", "required"
    )

    assert result.status == "HTTP 400 Bad Request"
    assert result.error_body == response_body.decode()
    rendered = f"{result.status}\n{result.error_body}"
    assert "Authorization" not in rendered
    assert "Bearer" not in rendered
