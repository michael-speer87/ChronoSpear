from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
chat: Any = importlib.import_module("chronospear_chat")
writer: Any = importlib.import_module("world_writer")
tools: Any = importlib.import_module("world_question_tools")
fixtures: Any = importlib.import_module("test_world_question")


def no_match(_world: str | Path, _question: str) -> Any:
    return tools.WorldRecognition(False, (), False)


def david_match(_world: str | Path, _question: str) -> Any:
    return tools.WorldRecognition(True, ("David Steele",), False)


def response(content: str | None = None, name: str | None = None, **arguments: str) -> Any:
    calls = ()
    if name is not None:
        calls = (writer.WriterToolCall("call", name, json.dumps(arguments)),)
    return writer.WriterProviderResult(
        content, calls, {"prompt_tokens": 5, "completion_tokens": 2}
    )


class ScriptedProvider:
    def __init__(self, *items: Any) -> None:
        self.items = iter(items)
        self.messages: list[list[dict[str, object]]] = []
        self.tool_choices: list[tuple[dict[str, object], ...]] = []

    def __call__(self, messages: list[dict[str, object]], schemas: Any) -> Any:
        self.messages.append([dict(item) for item in messages])
        self.tool_choices.append(schemas)
        return next(self.items)


def specialist(answer: str, *, grounded: bool = True) -> Any:
    return tools.ToolQuestionResult(
        question="world question",
        world="test",
        status="answered",
        answer=answer,
        evidence_ids=("HO-evidence",) if grounded else (),
        admitted_evidence={"HO-evidence": "support"} if grounded else {},
        navigation_trace=["LANGUAGE-ACTIVATE: David Steele", "submit_answer(...)"],
    )


def test_shallow_probe_recognizes_known_identity_without_leaking_or_mutating(
    tmp_path: Path,
) -> None:
    memory = fixtures._memory()
    memory["identities"].append(
        {
            "key": "e7",
            "kind": "ENTITY",
            "name": "David Steele",
            "synopsis": "A synopsis that must not leak.",
            "description": "A description that must not leak.",
        }
    )
    memory_path = tmp_path / "memory.json"
    memory_path.write_text(json.dumps(memory), encoding="utf-8")
    original = memory_path.read_bytes()

    recognition = tools.probe_world_recognition(
        tmp_path, "What can you tell me about David Steele?"
    )

    assert recognition == tools.WorldRecognition(True, ("David Steele",), False)
    payload = json.dumps(recognition.payload())
    assert "synopsis" not in payload.casefold()
    assert "description" not in payload.casefold()
    assert "history" not in payload.casefold()
    assert "association" not in payload.casefold()
    assert memory_path.read_bytes() == original


def test_shallow_probe_returns_clean_no_match(tmp_path: Path) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()

    recognition = tools.probe_world_recognition(
        package, "Explain a completely unrelated general subject."
    )

    assert recognition == tools.WorldRecognition(False, (), False)
    assert (package / "memory.json").read_bytes() == original


def test_world_question_routes_through_smeagol() -> None:
    outer = ScriptedProvider(
        response(name="ask_smeagol", request="Who is David Steele?"),
        response("David Steele is a figure established by the loaded world."),
    )
    requests: list[str] = []

    def smeagol(_world: Path, request: str, **_kwargs: object) -> Any:
        requests.append(request)
        return specialist("David Steele is established in CAM.")

    result = chat.run_chat_turn(
        "unused",
        "Who is David Steele?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=smeagol,
        recognition_probe=david_match,
    )

    assert result.status == "answered"
    assert requests == ["Who is David Steele?"]
    assert result.smeagol_queries == 1
    assert result.web_searches == 0
    assert result.trace[:2] == [
        "CAM-RECOGNITION: matched=true targets=David Steele ambiguous=false",
        "ask_smeagol('Who is David Steele?')",
    ]
    routing = str(outer.messages[0][1]["content"])
    assert '"matched": true' in routing
    assert '"targets": ["David Steele"]' in routing
    assert json.loads(str(outer.messages[1][-1]["content"]))["grounded"] is True
    assert {schema["function"]["name"] for schema in outer.tool_choices[0]} == {
        "ask_smeagol",
        "web_search",
    }


def test_world_proposal_uses_smeagol_then_returns_labeled_non_canon(
    tmp_path: Path,
) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()
    outer = ScriptedProvider(
        response(
            name="ask_smeagol",
            request="What existing David Steele canon is relevant to a new event?",
        ),
        response("David might face a choice between control and protecting Anna."),
    )

    result = chat.run_chat_turn(
        package,
        "Suggest a new Historical Occurrence for David Steele.",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: specialist(
            "Existing canon says David was transformed during the Pradhāna."
        ),
        recognition_probe=david_match,
    )

    assert result.status == "answered"
    assert result.outer_calls == 2
    assert result.smeagol_queries == 1
    assert result.web_searches == 0
    assert str(result.answer).startswith("Non-canonical proposal:")
    assert result.trace[-1] == "OUTER: generated grounded non-canonical proposal"
    tool_result = json.loads(str(outer.messages[1][-1]["content"]))
    assert "Existing canon" in tool_result["answer"]
    assert (package / "memory.json").read_bytes() == original


def test_recognized_proposal_cannot_finalize_before_injected_grounding() -> None:
    outer = ScriptedProvider(
        response("David becomes a cartographer in the Whispering Caves."),
        response("One non-canon possibility uses David's established Wolf abilities."),
    )
    requests: list[str] = []

    def smeagol(_world: Path, request: str, **_kwargs: object) -> Any:
        requests.append(request)
        return specialist(
            "David is an accountant who became The Wolf during the Pradhāna."
        )

    result = chat.run_chat_turn(
        "unused",
        "Suggest a new Historical Occurrence for David Steele's history.",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=smeagol,
        recognition_probe=david_match,
    )

    assert result.outer_calls == 2
    assert result.smeagol_queries == 1
    assert len(requests) == 1
    assert "David Steele" in requests[0]
    assert "Do not invent anything" in requests[0]
    assert "cartographer" not in str(result.answer)
    assert result.trace[1] == "GROUNDING-REQUIRED: recognized world proposal"
    assert outer.messages[1][-1]["role"] == "tool"


def test_smeagol_insufficient_still_allows_cautious_grounded_proposal() -> None:
    outer = ScriptedProvider(
        response("An unsupported proposal."),
        response(
            "As a non-canon proposal with limited known context, David could face "
            "a new choice without assuming any additional established backstory."
        ),
    )
    result = chat.run_chat_turn(
        "unused",
        "Suggest a possible future event for David Steele.",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: specialist(
            "Insufficient canonical detail.", grounded=False
        ),
        recognition_probe=david_match,
    )

    assert result.status == "answered"
    assert result.smeagol_queries == 1
    assert "limited known context" in str(result.answer)


def test_smeagol_failure_blocks_recognized_character_proposal() -> None:
    failed = tools.ToolQuestionResult(
        question="ground David",
        world="test",
        status="provider_failure",
        error="sanitized provider failure",
    )
    result = chat.run_chat_turn(
        "unused",
        "Suggest a new event for David Steele.",
        outer_provider=ScriptedProvider(response("Premature proposal.")),
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: failed,
        recognition_probe=david_match,
    )

    assert result.status == "grounding_failure"
    assert result.answer is None
    assert "won't invent" in str(result.error)
    assert result.smeagol_queries == 1


def test_generic_brainstorming_does_not_require_smeagol() -> None:
    result = chat.run_chat_turn(
        "unused",
        "Give me a random encounter idea.",
        outer_provider=ScriptedProvider(response("A bridge begins politely arguing.")),
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic brainstorming must not require Smeagol")
        ),
        recognition_probe=no_match,
    )

    assert result.status == "answered"
    assert result.smeagol_queries == 0


def test_ambiguous_proposal_requests_clarification_without_choosing() -> None:
    ambiguous = tools.WorldRecognition(
        True, ("David Steele", "David Steele Jr."), True
    )
    result = chat.run_chat_turn(
        "unused",
        "Suggest a new event for David.",
        outer_provider=ScriptedProvider(response("David explores somewhere.")),
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ambiguous target must not be chosen")
        ),
        recognition_probe=lambda *_args: ambiguous,
    )

    assert result.smeagol_queries == 0
    assert "ambiguous" in str(result.answer)
    assert "David Steele Jr." in str(result.answer)


def test_proposal_contract_does_not_assign_time_by_default() -> None:
    assert "Do not assign WorldTime, SystemTime, or a calendar date unless" in (
        chat.SYSTEM_PROMPT
    )


def test_architecture_advice_uses_only_current_cam_object_model() -> None:
    answer = (
        "Under the current CAM model, represent the capability as a Describer and "
        "an appropriate Association; use immutable Historical Occurrences to establish "
        "the initial transformation and the later change in WorldTime. This is design "
        "advice, not a claim that those additions are already canon."
    )
    result = chat.run_chat_turn(
        "unused",
        "How should I represent an ability in CAM?",
        outer_provider=ScriptedProvider(response(answer)),
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        recognition_probe=no_match,
    )

    assert result.answer == answer
    assert result.smeagol_queries == 0
    assert "AbilityNode" not in str(result.answer)
    assert "StateProperty" not in str(result.answer)
    assert "Do not invent AbilityNode, StateProperty, PropertyNode" in chat.SYSTEM_PROMPT


def test_outer_cli_keeps_groq_tool_choice_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeOuterProvider:
        def __init__(self, model: str, tool_choice: str) -> None:
            captured["model"] = model
            captured["tool_choice"] = tool_choice

    class FakeChat:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setattr(chat, "GroqWriterProvider", FakeOuterProvider)
    monkeypatch.setattr(chat, "_provider", lambda *_args: object())
    monkeypatch.setattr(chat, "ChronoSpearChat", FakeChat)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chronospear_chat.py",
            "--world",
            "unused",
            "--provider",
            "groq",
            "--model",
            "openai/gpt-oss-20b",
        ],
    )

    chat.main()

    assert captured == {
        "model": "openai/gpt-oss-20b",
        "tool_choice": "auto",
        "ran": True,
    }


def test_mixed_canon_and_design_keeps_planned_change_noncanonical() -> None:
    outer = ScriptedProvider(
        response(
            name="ask_smeagol",
            request="What does CAM currently establish about David's transformation?",
        ),
        response(
            "As a non-canonical design proposal, record the initial involuntary "
            "transformation and later voluntary control as separate Historical "
            "Occurrences, with a Describer and Association for the capability."
        ),
    )
    result = chat.run_chat_turn(
        "unused",
        "David was transformed involuntarily and later may gain control. "
        "How should I represent that?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: specialist(
            "CAM establishes the initial involuntary transformation only."
        ),
        recognition_probe=david_match,
    )

    assert result.smeagol_queries == 1
    assert "non-canonical design proposal" in str(result.answer)
    assert "separate Historical Occurrences" in str(result.answer)


def test_system_and_casual_questions_can_answer_without_tools() -> None:
    for question, answer in (
        ("What is CAM?", "CAM is Chrono Associative Memory."),
        ("Tell me a joke.", "A recursive joke calls itself."),
    ):
        result = chat.run_chat_turn(
            "unused",
            question,
            outer_provider=ScriptedProvider(response(answer)),
            smeagol_provider=object(),
            web_provider=chat.UnavailableWebSearchProvider(),
            smeagol_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("Smeagol must not be called")
            ),
            recognition_probe=no_match,
        )
        assert result.answer == answer
        assert result.smeagol_queries == 0


def test_insufficient_smeagol_result_is_preserved_by_outer_response() -> None:
    outer = ScriptedProvider(
        response(name="ask_smeagol", request="Did James know?"),
        response("CAM does not contain enough information to establish that."),
    )
    result = chat.run_chat_turn(
        "unused",
        "Did James know?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        smeagol_runner=lambda *_args, **_kwargs: specialist(
            "Insufficient evidence.", grounded=False
        ),
        recognition_probe=no_match,
    )

    payload = json.loads(str(outer.messages[1][-1]["content"]))
    assert payload == {
        "status": "answered",
        "answer": "Insufficient evidence.",
        "grounded": False,
    }
    assert result.answer == "Insufficient evidence."


class AvailableWeb:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str) -> Any:
        self.queries.append(query)
        return chat.WebSearchResult("ok", "A bounded external wolf result.")


def test_mixed_question_can_use_smeagol_and_web_in_one_turn() -> None:
    outer = ScriptedProvider(
        response(name="ask_smeagol", request="What does CAM say about David's Wolf form?"),
        response(name="web_search", query="current real gray wolf speed"),
        response("CAM and the external result can now be compared by domain."),
    )
    web = AvailableWeb()
    result = chat.run_chat_turn(
        "unused",
        "Would David's Wolf form be faster than a real wolf?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=web,
        smeagol_runner=lambda *_args, **_kwargs: specialist("David's canon result."),
        recognition_probe=david_match,
    )

    assert result.smeagol_queries == 1
    assert result.web_searches == 1
    assert web.queries == ["current real gray wolf speed"]
    assert result.status == "answered"


def test_unavailable_web_returns_explicit_tool_result() -> None:
    outer = ScriptedProvider(
        response(name="web_search", query="latest news"),
        response("I don't currently have configured live web search."),
    )
    result = chat.run_chat_turn(
        "unused",
        "What is the latest news?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        recognition_probe=no_match,
    )

    payload = json.loads(str(outer.messages[1][-1]["content"]))
    assert payload["status"] == "unavailable"
    assert "configured live web-search provider" in payload["result"]
    assert result.web_searches == 1
    assert result.smeagol_queries == 0


def test_followup_context_still_routes_canonical_request_through_fresh_smeagol() -> None:
    outer = ScriptedProvider(
        response(name="ask_smeagol", request="Did Anna witness David's transformation?"),
        response("Smeagol could not establish whether Anna witnessed it."),
    )
    results: list[Any] = []

    def smeagol(_world: Path, _request: str, **_kwargs: object) -> Any:
        value = specialist("Insufficient evidence.", grounded=False)
        results.append(value)
        return value

    result = chat.run_chat_turn(
        "unused",
        "Did Anna see it?",
        outer_provider=outer,
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        recent_context=(chat.ChatTurn("Who transformed?", "David transformed."),),
        smeagol_runner=smeagol,
        recognition_probe=no_match,
    )

    assert "David transformed" in str(outer.messages[0][1]["content"])
    assert len(results) == 1
    assert result.smeagol_queries == 1


class Inputs:
    def __init__(self, *items: str) -> None:
        self.items = iter(items)

    def __call__(self, _prompt: str) -> str:
        return next(self.items)


def test_terminal_smeagol_bypass_and_trace_do_not_use_outer_model(tmp_path: Path) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()
    calls: list[str] = []

    def smeagol(_world: Path, request: str, **_kwargs: object) -> Any:
        calls.append(request)
        return specialist("Direct specialist answer.")

    shell = chat.ChronoSpearChat(
        package,
        outer_provider=ScriptedProvider(),
        smeagol_provider=object(),
        web_provider=chat.UnavailableWebSearchProvider(),
        outer_model="mock",
        provider_name="mock",
        smeagol_runner=smeagol,
    )
    output: list[str] = []
    shell.run(
        Inputs("/trace on", "/smeagol Who is David?", "/stats", "/world", "/quit"),
        output.append,
    )

    assert calls == ["Who is David?"]
    assert "Smeagol > Direct specialist answer." in output
    assert "[smeagol trace]" in output
    assert "No query has run yet." in output
    assert (package / "memory.json").read_bytes() == original
