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


def test_opening_session_is_blank_and_performs_no_automatic_activation(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "a")
    )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "What connects Alric to others?",
        provider_fn=provider,
    )
    opening = provider.messages[0][-1]["content"]

    assert isinstance(opening, str)
    assert "What connects Alric to others?" in opening
    assert "No world facts have been retrieved yet" in opening
    assert "Dorf" not in opening
    assert "Royal Guard" not in opening
    assert "Stonebridge" not in opening
    assert "[A-" not in opening
    assert "[HO-" not in opening
    assert "Memory availability map" not in opening
    assert result.activations == 1
    assert result.initial_activations == 1
    assert result.explicit_activations == 0
    assert result.history_calls == 0
    assert result.association_calls == 0
    assert result.description_calls == 0
    assert result.cam_estimated_tokens == 0
    assert result.status == "answered"
    tool_names = {
        str(tool["function"]["name"])
        for tool in provider.tools[0]
        if isinstance(tool.get("function"), dict)
    }
    assert tool_names == {
        "search_memory",
        "activate",
        "get_history",
        "get_associations",
        "get_description",
        "suggest_node",
        "submit_answer",
    }


def language_package(tmp_path: Path) -> Path:
    memory = fixtures._memory()
    memory["identities"].extend(
        [
            {
                "key": "e7",
                "kind": "ENTITY",
                "name": "James Poole",
                "synopsis": "",
                "description": "James's full description.",
            },
            {
                "key": "e8",
                "kind": "ENTITY",
                "name": "Thomas Thompson",
                "synopsis": "",
                "description": "Thomas's full description.",
            },
            {
                "key": "e9",
                "kind": "ENTITY",
                "name": "The Pradhāna",
                "synopsis": "",
                "description": "Pradhāna's full description.",
            },
            {
                "key": "e10",
                "kind": "ENTITY",
                "name": "David Steele",
                "synopsis": "",
                "description": "David's full description.",
            },
            {
                "key": "e11",
                "kind": "ENTITY",
                "name": "David Steele Jr.",
                "synopsis": "",
                "description": "Junior's full description.",
            },
        ]
    )
    (tmp_path / "memory.json").write_text(json.dumps(memory), encoding="utf-8")
    return tmp_path


def test_language_surface_recognizes_query_handles_without_retrieval(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer")
    )
    question = "Did James Poole know what happened to Thomas during the Pradhāna?"

    result = tool_module.run_world_question_tools(
        language_package(tmp_path), question, provider_fn=provider
    )

    opening = str(provider.messages[0][-1]["content"])
    assert "ENTITY | James Poole" in opening
    assert "ENTITY | Thomas Thompson" in opening
    assert "ENTITY | The Pradhāna" in opening
    assert "full description" not in opening
    assert "[A-" not in opening
    assert "[HO-" not in opening
    assert result.language_matches == 3
    assert result.ambiguous_language_matches == 0
    assert result.activations == 3
    assert result.initial_activations == 3
    assert result.explicit_activations == 0
    assert result.history_calls == 0
    assert result.association_calls == 0
    assert result.description_calls == 0
    assert result.cam_estimated_tokens == 0
    assert result.admitted_evidence == {}
    assert result.admitted_descriptions == []


def test_language_surface_recognizes_simple_exact_identity_without_retrieval(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer")
    )

    result = tool_module.run_world_question_tools(
        language_package(tmp_path), "Who is David Steele?", provider_fn=provider
    )

    opening = str(provider.messages[0][-1]["content"])
    assert "Initial active memory handles:\n- ENTITY | David Steele" in opening
    assert "David Steele Jr." not in opening
    assert result.language_matches == 1
    assert result.activations == 1
    assert result.initial_activations == 1
    assert result.explicit_activations == 0
    assert result.admitted_evidence == {}


def test_language_surface_exposes_ambiguous_partial_name_without_choosing(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer")
    )

    result = tool_module.run_world_question_tools(
        language_package(tmp_path), "Which David was present?", provider_fn=provider
    )

    opening = str(provider.messages[0][-1]["content"])
    assert "David -> possible handles:" in opening
    assert "ENTITY | David Steele" in opening
    assert "ENTITY | David Steele Jr." in opening
    assert result.language_matches == 0
    assert result.ambiguous_language_matches == 1
    assert result.activations == 0
    assert result.initial_activations == 0


def test_recent_conversation_is_orientation_but_language_uses_current_question(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer")
    )

    result = tool_module.run_world_question_tools(
        language_package(tmp_path),
        "What happened to him?",
        provider_fn=provider,
        recent_context=(
            tool_module.RecentConversationTurn(
                "Who is David Steele?", "David Steele is an established person."
            ),
        ),
    )

    opening = str(provider.messages[0][-1]["content"])
    assert "Recent conversation (orientation only, not canonical evidence):" in opening
    assert "User: Who is David Steele?" in opening
    assert "Current question:\nWhat happened to him?" in opening
    assert "Initial active memory handles:\n- none" in opening
    assert result.language_matches == 0
    assert result.initial_activations == 0
    assert result.admitted_evidence == {}


def test_direct_first_activation_returns_normal_cam_orientation(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        call("activate", {"name": "Alric"}, "activate"),
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer"),
    )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path), "Tell me about the veteran.", provider_fn=provider
    )

    returned = str(provider.messages[1][-1]["content"])
    assert "Alric:" in returned
    assert "Memory availability map:" in returned
    assert result.activations == 1
    assert result.navigation_trace == ["activate('Alric')", "submit_answer(...)"]
    assert result.initial_activations == 0
    assert result.explicit_activations == 1


def test_search_returns_bounded_orientation_without_admitting_evidence(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        call("search_memory", {"query": "guard"}, "search"),
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer"),
    )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path), "Who protects the crown?", provider_fn=provider
    )

    search_result = str(provider.messages[1][-1]["content"])
    assert "ENTITY | Royal Guard | The crown's guard." in search_result
    assert "full production Description" not in search_result
    assert "[A-" not in search_result
    assert "[HO-" not in search_result
    assert "Memory availability map" not in search_result
    assert result.searches == 1
    assert result.activations == 0
    assert result.admitted_evidence == {}
    assert result.admitted_descriptions == []


def test_search_miss_is_recoverable_and_session_continues(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        call("search_memory", {"query": "nonexistent concept"}, "search"),
        call("activate", {"name": "Alric"}, "activate"),
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer"),
    )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path), "Who is relevant?", provider_fn=provider
    )

    assert "Results: 0" in str(provider.messages[1][-1]["content"])
    assert result.status == "answered"
    assert result.llm_calls == 3
    assert result.searches == 1
    assert result.activations == 1


def test_suggest_node_is_advisory_recorded_and_does_not_mutate_world(
    tmp_path: Path,
) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()
    provider = ScriptedProvider(
        call(
            "suggest_node",
            {
                "kind": "DESCRIBER",
                "name": "Brown Eyes",
                "reason": "A potentially persistent trait appears to be missing.",
                "evidence_ids": [],
            },
            "suggest",
        ),
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "answer"),
    )

    result = tool_module.run_world_question_tools(
        package, "What is missing?", provider_fn=provider
    )

    assert result.status == "answered"
    assert result.node_suggestions == 1
    assert result.suggestions == [
        tool_module.NodeSuggestion(
            "DESCRIBER",
            "Brown Eyes",
            "A potentially persistent trait appears to be missing.",
            (),
        )
    ]
    assert "canonical CAM is unchanged" in str(provider.messages[1][-1]["content"])
    assert (package / "memory.json").read_bytes() == original
    assert len(fixtures.import_world(package).identities.all()) == 6
    assert result.admitted_evidence == {}


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
            if self.calls <= 6:
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
    assert result.history_calls == 6
    assert len(captured_ids) == len(set(captured_ids))
    assert result.evidence_ids[0] in result.admitted_evidence
    assert (package / "memory.json").read_bytes() == original
    assert result.navigation_trace == [
        "LANGUAGE: Alric -> Alric",
        "LANGUAGE-ACTIVATE: Alric",
        "LANGUAGE: Royal Guard -> Royal Guard",
        "LANGUAGE-ACTIVATE: Royal Guard",
        *("get_history('Alric')" for _ in range(6)),
        "submit_answer(...)",
    ]
    assert result.initial_activations == 2
    assert result.explicit_activations == 0


def test_unknown_identity_tool_call_fails_clearly(tmp_path: Path) -> None:
    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "Tell me about Alric.",
        provider_fn=ScriptedProvider(call("get_history", {"name": "Nobody"}, "h")),
        max_rounds=1,
    )

    assert result.status == "max_rounds"
    assert "Nobody" in result.transcript[-1].content


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
        max_rounds=1,
    )

    class ImmediateProvider:
        calls = 0

        def __call__(self, messages: list[dict[str, object]], _tools: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                return call("get_history", {"name": "Alric"}, "history")
            identifier = re.search(r"\[(HO-[0-9a-f-]+)\]", str(messages[-1]["content"]))
            assert identifier is not None
            return call(
                "submit_answer",
                {"answer": "Directly supported.", "evidence_ids": [identifier.group(1)]},
                "a",
            )

    valid = tool_module.run_world_question_tools(
        package, "What happened to Alric?", provider_fn=ImmediateProvider()
    )

    assert invalid.status == "max_rounds"
    assert "unadmitted evidence IDs" in invalid.transcript[-1].content
    assert valid.status == "answered"
    assert valid.llm_calls == 2
    assert valid.cam_tool_calls == 2


def test_submit_answer_terminates_and_max_rounds_stops_runaway_calls(
    tmp_path: Path,
) -> None:
    answer_provider = ScriptedProvider(
        call("submit_answer", {"answer": "Insufficient evidence.", "evidence_ids": []}, "a"),
        call("get_history", {"name": "Alric"}, "unused"),
    )
    answered = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "Tell me about the veteran.",
        provider_fn=answer_provider,
    )
    bounded = tool_module.run_world_question_tools(
        tmp_path,
        "Tell me about Alric.",
        provider_fn=ScriptedProvider(call("activate", {"name": "Alric"}, "a")),
        max_rounds=1,
    )

    assert answered.status == "answered"
    assert answered.llm_calls == 1
    assert bounded.status == "max_rounds"
    assert bounded.llm_calls == 1
    assert bounded.activations == 1


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
        max_rounds=1,
    )

    assert result.status == "max_rounds"
    assert result.structured_tool_calls_present is False
    diagnostic = next(
        item
        for item in result.transcript
        if (item.sender, item.recipient) == ("LIBRARIAN", "HARNESS")
    )
    assert (diagnostic.sender, diagnostic.recipient) == ("LIBRARIAN", "HARNESS")
    assert json.loads(diagnostic.content) == {"content": attempted}
    assert "role" not in diagnostic.content
    tool_module.print_transcript(result)
    printed = capsys.readouterr().out
    assert attempted in printed
    assert "structured tool_calls field present=False" in printed


def test_zero_tool_turn_is_corrected_and_may_recover_with_submit_answer(
    tmp_path: Path,
) -> None:
    class RecoveringProvider:
        calls = 0

        def __call__(self, messages: list[dict[str, object]], _tools: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(content="I should answer.", tool_calls=(), usage={})
            assert "No tool call was made" in str(messages[-1]["content"])
            return call(
                "submit_answer",
                {
                    "answer": "Insufficient evidence.",
                    "evidence_ids": [],
                },
                "answer",
            )

    result = tool_module.run_world_question_tools(
        fixtures._package(tmp_path),
        "What happened to Alric?",
        provider_fn=RecoveringProvider(),
    )

    assert result.status == "answered"
    assert result.llm_calls == 2
    assert ("HARNESS", "LIBRARIAN") in [
        (item.sender, item.recipient) for item in result.transcript
    ]


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
