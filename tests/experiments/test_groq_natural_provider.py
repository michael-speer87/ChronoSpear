from collections.abc import Mapping

import pytest

from chronospear.experiments.groq_natural_provider import (
    NATURAL_LANGUAGE_SYSTEM_PROMPT,
    GroqNaturalLanguageProvider,
)
from chronospear.experiments.groq_provider import GroqProviderError
from chronospear.experiments.natural_language_cam import (
    ConversationMessage,
    NaturalLanguageProviderRequest,
)


class CaptureTransport:
    def __init__(self) -> None:
        self.payload: Mapping[str, object] | None = None

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> tuple[Mapping[str, object], float]:
        self.payload = payload
        return (
            {
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {"message": {"content": "Where is Archivist Sol based?"}}
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 6,
                    "total_time": 0.1,
                },
            },
            0.2,
        )


def test_natural_provider_uses_plain_text_protocol_without_internal_options() -> None:
    transport = CaptureTransport()
    provider = GroqNaturalLanguageProvider(api_key="test-key", transport=transport)
    request = NaturalLanguageProviderRequest(
        call_number=1,
        messages=(
            ConversationMessage(
                "user",
                "ACTION\nWhere should Nera go?\n\n"
                "BOUNDED CAM EVIDENCE\nENTITY | Archivist Sol",
            ),
        ),
        evidence=("ENTITY | Archivist Sol",),
    )

    response = provider(request)

    assert response.raw_text == "Where is Archivist Sol based?"
    assert transport.payload is not None
    assert "response_format" not in transport.payload
    messages = transport.payload["messages"]
    rendered = str(messages)
    assert NATURAL_LANGUAGE_SYSTEM_PROMPT in rendered
    assert "association:A1" not in rendered
    assert "node:stonebridge" not in rendered
    assert "selectors" not in rendered.casefold()


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_failure_retains_response_diagnostics(content: object) -> None:
    diagnostic_body: Mapping[str, object] = {
        "id": "chatcmpl-diagnostic",
        "model": "openai/gpt-oss-20b",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning": "Reasoning consumed the available completion budget.",
                    "tool_calls": [],
                    "refusal": None,
                },
                "finish_reason": "length",
            }
        ],
        "usage": {
            "prompt_tokens": 40,
            "completion_tokens": 180,
            "total_time": 0.3,
        },
        "x_groq": {"id": "request-diagnostic"},
    }

    def transport(
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> tuple[Mapping[str, object], float]:
        return diagnostic_body, 0.4

    provider = GroqNaturalLanguageProvider(api_key="test-key", transport=transport)
    request = NaturalLanguageProviderRequest(
        call_number=1,
        messages=(ConversationMessage("user", "ACTION\nInvestigate."),),
        evidence=(),
    )

    with pytest.raises(GroqProviderError, match="non-empty text") as caught:
        provider(request)

    assert caught.value.wall_latency_seconds == 0.4
    assert caught.value.response_body is diagnostic_body
    assert caught.value.response_body["choices"] == diagnostic_body["choices"]
    assert caught.value.response_body["usage"] == diagnostic_body["usage"]
