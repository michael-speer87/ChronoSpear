from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
tool_module: Any = importlib.import_module("world_question_tools")
writer_module: Any = importlib.import_module("world_writer")
fixtures: Any = importlib.import_module("test_world_question")


def call(name: str, arguments: dict[str, object], call_id: str) -> Any:
    return writer_module.WriterProviderResult(
        None,
        (writer_module.WriterToolCall(call_id, name, json.dumps(arguments)),),
        {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
    )


class ScriptedProvider:
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


def test_opening_packet_keeps_global_budget_and_omits_text_control_surface(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "a")
    )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "What connects Alric, Dorf, Royal Guard, and Stonebridge?",
        provider_fn=provider,
    )
    opening = provider.messages[0][-1]["content"]

    assert isinstance(opening, str)
    assert opening.count("- [A-") == 3
    assert opening.count("- [HO-") == 5
    assert "CAM CONTROL SURFACE" not in opening
    assert "Valid EXPAND commands" not in opening
    assert result.status == "answered"


def test_repeated_history_tools_advance_without_repeats_and_then_answer(
    tmp_path: Path,
) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()
    captured_ids: list[str] = []

    class HistoryProvider:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, messages: list[dict[str, object]], _tools: Any) -> Any:
            self.calls += 1
            if self.calls <= 2:
                return call("get_history", {"name": "Alric"}, f"h{self.calls}")
            for message in messages:
                if message.get("role") == "tool":
                    content = message["content"]
                    assert isinstance(content, str)
                    captured_ids.extend(re.findall(r"\[(HO-[0-9a-f-]+)\]", content))
            first_patrol = next(
                identifier
                for message in messages
                if message.get("role") == "tool"
                for identifier in re.findall(
                    r"\[(HO-[0-9a-f-]+)\].*first Royal Guard patrol", str(message["content"])
                )
            )
            return call(
                "submit_answer",
                {"answer": "The patrol began at North Gate.", "evidence_ids": [first_patrol]},
                "answer",
            )

    result = tool_module.run_world_question_tools(
        package,
        "Where did Alric's first Royal Guard patrol begin?",
        provider_fn=HistoryProvider(),
    )

    assert result.status == "answered"
    assert result.history_calls == 2
    assert len(captured_ids) == len(set(captured_ids))
    assert result.evidence_ids[0] in result.admitted_evidence
    assert (package / "memory.json").read_bytes() == original
    assert [(item.sender, item.recipient) for item in result.transcript][-5:] == [
        ("LIBRARIAN", "CAM TOOL"),
        ("CAM TOOL", "LIBRARIAN"),
        ("LIBRARIAN", "CAM TOOL"),
        ("CAM TOOL", "LIBRARIAN"),
        ("LIBRARIAN", "ANSWER TOOL"),
    ]


def test_unknown_identity_tool_call_fails_clearly(tmp_path: Path) -> None:
    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "Tell me about Alric.",
        provider_fn=ScriptedProvider(call("get_history", {"name": "Nobody"}, "h")),
    )

    assert result.status == "tool_failure"
    assert "Nobody" in result.error


def test_unadmitted_evidence_fails_and_valid_admitted_evidence_succeeds(
    tmp_path: Path,
) -> None:
    package = fixtures._package(tmp_path)
    invalid = tool_module.run_world_question_tools(
        package,
        "What happened to Alric?",
        provider_fn=ScriptedProvider(
            call("submit_answer", {"answer": "Unsupported.", "evidence_ids": ["HO-fake"]}, "a")
        ),
    )

    class ImmediateProvider:
        def __call__(self, messages: list[dict[str, object]], _tools: Any) -> Any:
            opening = str(messages[-1]["content"])
            identifier = re.search(r"\[(HO-[0-9a-f-]+)\]", opening)
            assert identifier is not None
            return call(
                "submit_answer",
                {"answer": "Directly supported.", "evidence_ids": [identifier.group(1)]},
                "a",
            )

    valid = tool_module.run_world_question_tools(
        package, "What happened to Alric?", provider_fn=ImmediateProvider()
    )

    assert invalid.status == "tool_failure"
    assert "unadmitted evidence IDs" in invalid.error
    assert valid.status == "answered"
    assert valid.llm_calls == 1
    assert valid.cam_tool_calls == 1


def test_submit_answer_terminates_and_max_rounds_stops_runaway_calls(
    tmp_path: Path,
) -> None:
    answer_provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "a"),
        call("get_history", {"name": "Alric"}, "unused"),
    )
    answered = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "Tell me about Alric.",
        provider_fn=answer_provider,
    )
    bounded = tool_module.run_world_question_tools(
        tmp_path,
        "Tell me about Alric.",
        provider_fn=ScriptedProvider(call("get_history", {"name": "Alric"}, "h")),
        max_rounds=1,
    )

    assert answered.status == "answered"
    assert answered.llm_calls == 1
    assert bounded.status == "max_rounds"
    assert bounded.llm_calls == 1
    assert bounded.history_calls == 1


def test_tool_protocol_failure_preserves_sanitized_raw_assistant_message(
    tmp_path: Path,
    capsys: Any,
) -> None:
    attempted = "EXPAND Alric HISTORY"
    response = SimpleNamespace(
        content=attempted,
        tool_calls=(),
        usage={},
        raw_assistant_message={"role": "assistant", "content": attempted},
        tool_calls_present=False,
    )
    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "Where did Alric's first patrol begin?",
        provider_fn=ScriptedProvider(response),
    )

    assert result.status == "tool_protocol_failure"
    assert result.structured_tool_calls_present is False
    diagnostic = result.transcript[-1]
    assert (diagnostic.sender, diagnostic.recipient) == ("LIBRARIAN", "HARNESS")
    assert json.loads(diagnostic.content) == {"content": attempted}
    assert "role" not in diagnostic.content
    tool_module.print_transcript(result)
    printed = capsys.readouterr().out
    assert attempted in printed
    assert "structured tool_calls field present=False" in printed


def test_cli_forwards_configured_llama_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel_result = object()

    class FakeLlamaProvider:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    def fake_run(*_args: object, **kwargs: object) -> object:
        captured["provider"] = kwargs["provider_fn"]
        return sentinel_result

    monkeypatch.setattr(tool_module, "LlamaCppToolProvider", FakeLlamaProvider)
    monkeypatch.setattr(tool_module, "run_world_question_tools", fake_run)
    monkeypatch.setattr(
        tool_module,
        "print_transcript",
        lambda result: captured.update(printed=result),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "world_question_tools.py",
            "--world",
            "unused-world",
            "--question",
            "Where?",
            "--provider",
            "llama-cpp",
            "--llama-timeout",
            "300",
        ],
    )

    tool_module.main()

    assert captured["timeout_seconds"] == 300.0
    assert captured["printed"] is sentinel_result
