import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from io import BytesIO

import pytest

from chronospear.experiments.cam_llm import ProviderRequest
from chronospear.experiments.groq_provider import (
    GroqProvider,
    GroqProviderError,
    _default_transport,
)


class StubTransport:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = response
        self.payloads: list[Mapping[str, object]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> tuple[Mapping[str, object], float]:
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["User-Agent"] == "ChronoSpear-CAM-Experiment/0.1"
        assert timeout_seconds == 30
        self.payloads.append(payload)
        return self.response, 0.25


def _api_response(content: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "model": "openai/gpt-oss-20b",
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {
            "prompt_tokens": 101,
            "completion_tokens": 17,
            "total_time": 0.125,
        },
    }


def test_groq_provider_parses_conclusion_usage_model_and_latency() -> None:
    transport = StubTransport(
        _api_response({"kind": "conclusion", "text": "Alric reports to Captain Mira."})
    )
    provider = GroqProvider(
        api_key="test-key",
        expansion_selectors=("association:A3",),
        transport=transport,
    )

    response = provider(ProviderRequest("Who receives the report?", ("NODE alric",), 1))

    assert response.text == "Alric reports to Captain Mira."
    assert response.input_tokens == 101
    assert response.output_tokens == 17
    assert response.model == "openai/gpt-oss-20b"
    assert response.provider_latency_seconds == 0.125
    assert response.wall_latency_seconds == 0.25
    assert transport.payloads[0]["response_format"] == {"type": "json_object"}


def test_groq_provider_parses_expansion_request() -> None:
    provider = GroqProvider(
        api_key="test-key",
        expansion_selectors=("association:A3",),
        transport=StubTransport(
            _api_response(
                {
                    "kind": "expand",
                    "selectors": ["association:A3"],
                    "reason": "Need the reporting relationship.",
                }
            )
        ),
    )

    response = provider(ProviderRequest("Who receives the report?", ("NODE alric",), 1))

    assert response.kind == "expand"
    assert response.selectors == ("association:A3",)
    assert response.reason == "Need the reporting relationship."


def test_groq_provider_prompt_does_not_claim_initial_evidence_is_sufficient() -> None:
    transport = StubTransport(_api_response({"kind": "conclusion", "text": "Done."}))
    provider = GroqProvider(
        api_key="test-key",
        expansion_selectors=("association:A3",),
        transport=transport,
    )

    provider(ProviderRequest("Conclude.", ("EVIDENCE",), 1))

    messages = transport.payloads[0]["messages"]
    prompt = json.dumps(messages)
    assert "initial evidence is sufficient" not in prompt.lower()
    assert "association:A3" in prompt


def test_groq_provider_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(GroqProviderError, match="GROQ_API_KEY"):
        GroqProvider(expansion_selectors=())


def test_http_failure_records_client_wall_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        "https://api.groq.com/openai/v1/chat/completions",
        400,
        "Bad Request",
        Message(),
        BytesIO(b'{"error":"invalid"}'),
    )

    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    times = iter((10.0, 10.75))
    monkeypatch.setattr(time, "perf_counter", lambda: next(times))

    with pytest.raises(GroqProviderError, match="Groq HTTP 400") as caught:
        _default_transport("https://example.test", {}, {}, 30)

    assert caught.value.wall_latency_seconds == 0.75


def test_url_failure_records_client_wall_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.URLError("name resolution failed")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    times = iter((20.0, 20.125))
    monkeypatch.setattr(time, "perf_counter", lambda: next(times))

    with pytest.raises(GroqProviderError, match="name resolution failed") as caught:
        _default_transport("https://example.test", {}, {}, 30)

    assert caught.value.wall_latency_seconds == 0.125
