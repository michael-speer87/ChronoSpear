from __future__ import annotations

import importlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
writer_module: Any = importlib.import_module("world_writer")
provider_module: Any = importlib.import_module("cam_native_provider")
tool_question_module: Any = importlib.import_module("world_question_tools")


def _package(tmp_path: Path) -> Path:
    memory = {
        "identities": [
            {
                "key": "e1",
                "kind": "ENTITY",
                "name": "Alric",
                "synopsis": "A veteran guard.",
                "description": "Alric is a veteran member of the Royal Guard.",
            },
            {
                "key": "p1",
                "kind": "PLACE",
                "name": "Stonebridge",
                "synopsis": "A fortified settlement.",
                "description": "Stonebridge is an old fortified settlement.",
            },
            {
                "key": "e2",
                "kind": "ENTITY",
                "name": "Royal Guard",
                "synopsis": "The crown's guard.",
                "description": "The Royal Guard protects the crown.",
            },
            {
                "key": "e3",
                "kind": "ENTITY",
                "name": "Elara",
                "synopsis": "A wizard elsewhere in the world.",
                "description": "Elara is not involved in this scene.",
            },
        ],
        "associations": [
            {
                "key": "a1",
                "source": "e1",
                "relationship": "MEMBER_OF",
                "target": "e2",
            }
        ],
        "historical_occurrences": [
            {
                "key": "ho1",
                "participants": ["e1"],
                "place": "p1",
                "world_time": 100,
                "system_time": 1,
                "synopsis": "Alric joined the Royal Guard.",
                "story": "Alric joined the Royal Guard at Stonebridge.",
                "started_associations": ["a1"],
                "ended_associations": [],
            }
        ],
    }
    (tmp_path / "memory.json").write_text(json.dumps(memory), encoding="utf-8")
    return tmp_path


def memory_call(request: str, call_id: str = "memory-1") -> Any:
    return writer_module.WriterProviderResult(
        None,
        (
            writer_module.WriterToolCall(
                call_id, "memory", json.dumps({"request": request})
            ),
        ),
        {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    )


def final_scene(text: str) -> Any:
    return writer_module.WriterProviderResult(
        text,
        (),
        {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    )


class ScriptedWriter:
    def __init__(self, *responses: Any) -> None:
        self.responses = iter(responses)
        self.messages: list[list[dict[str, object]]] = []
        self.tools: list[tuple[dict[str, object], ...]] = []

    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> Any:
        self.messages.append([dict(message) for message in messages])
        self.tools.append(tools)
        return next(self.responses)


class EvidenceAnsweringLibrarian:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> Any:
        self.messages.append([dict(message) for message in messages])
        packet = messages[-1]["content"]
        match = re.search(r"\[((?:A|HO)-[0-9a-f-]+)\]", packet)
        evidence = match.group(1) if match else "none"
        return provider_module.ProviderResult(
            f"ANSWER: Production CAM supplied the requested canon.\nEVIDENCE: {evidence}",
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


class ToolCallingLibrarian:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages: list[dict[str, object]], tools: Any) -> Any:
        self.calls += 1
        assert tools is tool_question_module.CAM_TOOLS
        if self.calls == 1:
            return memory_call_for_librarian(
                "activate", {"name": "Elara"}, "activate-1"
            )
        evidence = next(
            match.group(1)
            for message in messages
            for match in re.finditer(
                r"\[(HO-[0-9a-f-]+)\]", str(message.get("content", ""))
            )
        )
        return memory_call_for_librarian(
            "submit_answer",
            {
                "answer": "The admitted canon supports the requested scene.",
                "evidence_ids": [evidence],
            },
            "answer-1",
        )


def memory_call_for_librarian(
    name: str, arguments: dict[str, object], call_id: str
) -> Any:
    return writer_module.WriterProviderResult(
        None,
        (writer_module.WriterToolCall(call_id, name, json.dumps(arguments)),),
        {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    )


@pytest.mark.parametrize("tool_choice", ["auto", "required"])
def test_groq_writer_forwards_tool_choice_and_redacts_http_error(
    monkeypatch: pytest.MonkeyPatch,
    tool_choice: str,
) -> None:
    api_key = "secret-test-key"
    response_body = b'{"error":{"message":"request blocked"}}'
    captured_request: urllib.request.Request | None = None

    def fail(request: urllib.request.Request, *, timeout: int) -> Any:
        nonlocal captured_request
        captured_request = request
        assert timeout == 60
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            Message(),
            io.BytesIO(response_body),
        )

    monkeypatch.setenv("GROQ_API_KEY", api_key)
    monkeypatch.setattr(writer_module.urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as error:
        writer_module.GroqWriterProvider("writer-model", tool_choice)(
            [], writer_module.WRITER_TOOLS
        )

    assert str(error.value) == f"Groq HTTP 403: {response_body.decode()}"
    assert api_key not in str(error.value)
    assert captured_request is not None
    request_body = json.loads(captured_request.data.decode())
    assert request_body["tool_choice"] == tool_choice
    assert captured_request.get_header("Authorization") == f"Bearer {api_key}"
    assert captured_request.get_header("Content-type") == "application/json"
    assert (
        captured_request.get_header("User-agent")
        == "ChronoSpear-Research/2026-08-31"
    )
    assert captured_request.get_method() == "POST"


@pytest.mark.parametrize(
    ("headers", "body", "expected_delay"),
    [
        ({"Retry-After": "2.5"}, b"rate limited", 2.6),
        ({}, b"Please try again in 1.75s", 1.85),
    ],
)
def test_groq_429_retries_same_request_with_reported_delay(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    body: bytes,
    expected_delay: float,
) -> None:
    requests: list[urllib.request.Request] = []
    delays: list[float] = []

    class Success:
        def __enter__(self) -> Success:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "Finished.", "tool_calls": []}}],
                    "usage": {},
                }
            ).encode()

    def urlopen(request: urllib.request.Request, *, timeout: int) -> Any:
        requests.append(request)
        if len(requests) == 1:
            message = Message()
            for key, value in headers.items():
                message[key] = value
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                message,
                io.BytesIO(body),
            )
        return Success()

    monkeypatch.setenv("GROQ_API_KEY", "secret")
    monkeypatch.setattr(writer_module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(writer_module.time, "sleep", delays.append)

    result = writer_module.GroqWriterProvider("writer-model")(
        [], writer_module.WRITER_TOOLS
    )

    assert len(requests) == 2
    assert requests[0].data == requests[1].data
    assert delays == pytest.approx([expected_delay])
    assert result.usage["provider_retries"] == 1


def test_writer_memory_request_is_forwarded_as_natural_language_to_real_harness(
    tmp_path: Path,
) -> None:
    request = "  What established history connects Alric to the Royal Guard?\n"
    writer = ScriptedWriter(memory_call(request), final_scene("Alric remembered his oath."))
    librarian = EvidenceAnsweringLibrarian()

    result = writer_module.run_world_writer(
        _package(tmp_path),
        "Write an interaction.",
        writer_provider=writer,
        librarian_provider=librarian,
    )

    assert result.status == "scene"
    assert request in librarian.messages[0][-1]["content"]
    assert len(writer.tools[0]) == 1
    function = writer.tools[0][0]["function"]
    assert isinstance(function, dict)
    assert function["name"] == "memory"
    assert "CHRONOSPEAR PRODUCTION CAM PACKET" in librarian.messages[0][-1]["content"]
    assert writer.messages[1][-1]["role"] == "tool"
    tool_result = writer.messages[1][-1]["content"]
    assert isinstance(tool_result, str)
    assert "CANON RESPONSE" in tool_result
    assert "Supporting evidence:" in tool_result
    assert "[A-" in tool_result


@pytest.mark.parametrize(
    "memory_request",
    [
        "ACTIVATE Alric",
        "EXPAND Alric HISTORY",
    ],
)
def test_writer_cannot_drive_cam_protocol_directly(memory_request: str) -> None:
    with pytest.raises(ValueError):
        writer_module.parse_writer_response(memory_call(memory_request))


def test_plain_text_is_final_and_never_drives_cam(tmp_path: Path) -> None:
    librarian = EvidenceAnsweringLibrarian()
    result = writer_module.run_world_writer(
        _package(tmp_path),
        "Write.",
        writer_provider=ScriptedWriter(final_scene("ACTIVATE Alric")),
        librarian_provider=librarian,
    )

    assert result.status == "scene"
    assert result.scene == "ACTIVATE Alric"
    assert librarian.messages == []


def test_writer_can_make_multiple_fresh_librarian_queries(tmp_path: Path) -> None:
    writer = ScriptedWriter(
        memory_call("What happened to Alric?", "memory-1"),
        memory_call("What is Stonebridge?", "memory-2"),
        final_scene("The old stones framed their conversation."),
    )
    librarian = EvidenceAnsweringLibrarian()

    result = writer_module.run_world_writer(
        _package(tmp_path),
        "Write a scene.",
        writer_provider=writer,
        librarian_provider=librarian,
    )

    assert result.status == "scene"
    assert result.librarian.queries == 2
    assert len(librarian.messages) == 2
    assert all(len(messages) == 2 for messages in librarian.messages)


def test_description_only_answer_passes_admitted_description_not_cam_controls(
    tmp_path: Path,
) -> None:
    writer = ScriptedWriter(
        memory_call("What is Stonebridge?"), final_scene("Stone walls rose nearby.")
    )

    def description_librarian(_messages: list[dict[str, str]]) -> Any:
        return provider_module.ProviderResult(
            "ANSWER: Stonebridge is a fortified settlement.\nEVIDENCE: none",
            {},
        )

    result = writer_module.run_world_writer(
        _package(tmp_path),
        "Write.",
        writer_provider=writer,
        librarian_provider=description_librarian,
    )
    canon = next(
        item.content
        for item in result.transcript
        if item.sender == "MEMORY TOOL" and item.recipient == "WRITER"
    )

    assert "DESCRIPTION Stonebridge: Stonebridge is an old fortified settlement." in canon
    assert "CAM CONTROL SURFACE" not in canon
    assert "Valid EXPAND commands" not in canon


def test_text_ends_loop_and_empty_output_fails(tmp_path: Path) -> None:
    scene = writer_module.run_world_writer(
        _package(tmp_path),
        "Write.",
        writer_provider=ScriptedWriter(final_scene("Finished prose.")),
        librarian_provider=EvidenceAnsweringLibrarian(),
    )
    malformed = writer_module.run_world_writer(
        tmp_path,
        "Write.",
        writer_provider=ScriptedWriter(final_scene("")),
        librarian_provider=EvidenceAnsweringLibrarian(),
    )

    assert scene.status == "scene"
    assert scene.scene == "Finished prose."
    assert scene.writer.calls == 1
    assert malformed.status == "writer_protocol_failure"


def test_writer_and_librarian_query_limits_stop_runaway_loops(tmp_path: Path) -> None:
    query_limited = writer_module.run_world_writer(
        _package(tmp_path),
        "Write.",
        writer_provider=ScriptedWriter(
            memory_call("What happened to Alric?", "memory-1"),
            memory_call("What is Stonebridge?", "memory-2"),
        ),
        librarian_provider=EvidenceAnsweringLibrarian(),
        max_librarian_queries=1,
    )
    turn_limited = writer_module.run_world_writer(
        tmp_path,
        "Write.",
        writer_provider=ScriptedWriter(memory_call("What happened to Alric?")),
        librarian_provider=EvidenceAnsweringLibrarian(),
        max_writer_turns=1,
    )

    assert query_limited.status == "librarian_query_limit"
    assert query_limited.librarian.queries == 1
    assert turn_limited.status == "writer_turn_limit"


def test_transcript_telemetry_and_memory_immutability_are_layered(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    original = (package / "memory.json").read_bytes()
    result = writer_module.run_world_writer(
        package,
        "Write.",
        writer_provider=ScriptedWriter(
            memory_call("What happened to Alric?"), final_scene("Finished.")
        ),
        librarian_provider=EvidenceAnsweringLibrarian(),
    )

    boundaries = [(item.sender, item.recipient) for item in result.transcript]
    assert boundaries[0] == ("USER", "WRITER")
    assert boundaries[1] == ("WRITER", "MEMORY TOOL")
    assert ("CAM", "MINI-IGOR") in boundaries
    assert ("MINI-IGOR", "CAM") in boundaries
    assert ("MEMORY TOOL", "WRITER") in boundaries
    assert boundaries[-1] == ("WRITER", "USER")
    assert result.writer.calls == 2
    assert result.writer.prompt_tokens == 40
    assert result.librarian.queries == 1
    assert result.librarian.mini_igor_calls == 1
    assert result.librarian.prompt_tokens == 10
    assert result.cam.activation_count == 1
    assert result.cam.estimated_packet_tokens > 0
    assert (package / "memory.json").read_bytes() == original


def test_writer_memory_tool_reuses_tool_driven_librarian_end_to_end(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    original = (package / "memory.json").read_bytes()
    librarian = ToolCallingLibrarian()
    writer = ScriptedWriter(
        memory_call("What canon supports Alric's Royal Guard interaction?"),
        final_scene("Alric and his officer reflected on their shared past."),
    )

    result = writer_module.run_world_writer(
        package,
        "Write the interaction.",
        writer_provider=writer,
        librarian_provider=librarian,
        librarian_runner=tool_question_module.run_world_question_tools,
    )

    boundaries = [(item.sender, item.recipient) for item in result.transcript]
    assert result.status == "scene"
    assert ("WRITER", "MEMORY TOOL") in boundaries
    assert ("LIBRARIAN", "CAM TOOL") in boundaries
    assert ("CAM TOOL", "LIBRARIAN") in boundaries
    assert ("LIBRARIAN", "ANSWER TOOL") in boundaries
    assert ("MEMORY TOOL", "WRITER") in boundaries
    assert boundaries[-1] == ("WRITER", "USER")
    assert result.librarian.queries == 1
    assert result.librarian.mini_igor_calls == 2
    assert result.librarian.cam_tool_calls == 2
    assert result.cam.activation_count >= 2
    assert result.cam.estimated_packet_tokens > 0
    canon = writer.messages[-1][-1]["content"]
    assert isinstance(canon, str)
    assert "CANON RESPONSE" in canon
    assert (package / "memory.json").read_bytes() == original


def test_exhausted_librarian_provider_failure_never_reaches_writer(
    tmp_path: Path,
) -> None:
    failed = tool_question_module.ToolQuestionResult(
        question="What happened to Alric?",
        world=str(tmp_path),
        status="provider_failure",
        error="Groq HTTP 429: still rate limited",
    )
    writer = ScriptedWriter(memory_call("What happened to Alric?"))

    result = writer_module.run_world_writer(
        _package(tmp_path),
        "Write.",
        writer_provider=writer,
        librarian_provider=EvidenceAnsweringLibrarian(),
        librarian_runner=lambda *_args, **_kwargs: failed,
    )

    assert result.status == "librarian_provider_failure"
    assert result.error == "Groq HTTP 429: still rate limited"
    assert len(writer.messages) == 1
    assert not any(
        item.sender == "MEMORY TOOL" and item.recipient == "WRITER"
        for item in result.transcript
    )
