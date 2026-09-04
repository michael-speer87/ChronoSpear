from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from chronospear.world_import import import_world

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
adapter_module: Any = importlib.import_module("production_cam_adapter")
question_module: Any = importlib.import_module("world_question")
provider_module: Any = importlib.import_module("cam_native_provider")


def _memory() -> dict[str, Any]:
    identities = [
        {
            "key": "e1",
            "kind": "ENTITY",
            "name": "Alric",
            "synopsis": "A veteran fighter.",
            "description": "Alric's full production Description.",
        },
        {
            "key": "e2",
            "kind": "ENTITY",
            "name": "Elara",
            "synopsis": "A human wizard.",
            "description": "Elara's full production Description.",
        },
        {
            "key": "e3",
            "kind": "ENTITY",
            "name": "Dorf",
            "synopsis": "A dwarven fighter.",
            "description": "Dorf's full production Description.",
        },
        {
            "key": "e4",
            "kind": "ENTITY",
            "name": "Royal Guard",
            "synopsis": "The crown's guard.",
            "description": "Royal Guard's full production Description.",
        },
        {
            "key": "p1",
            "kind": "PLACE",
            "name": "Stonebridge",
            "synopsis": "A fortified settlement.",
            "description": "Stonebridge's full production Description.",
        },
        {
            "key": "p2",
            "kind": "PLACE",
            "name": "North Gate",
            "synopsis": "Stonebridge's northern gate.",
            "description": "North Gate is Stonebridge's northern gate.",
        },
    ]
    associations = [
        {
            "key": "a1",
            "source": "e1",
            "relationship": "MEMBER_OF",
            "target": "e4",
        },
        {
            "key": "a2",
            "source": "e1",
            "relationship": "OPPOSES",
            "target": "e3",
        },
        {
            "key": "a3",
            "source": "e3",
            "relationship": "OPPOSES",
            "target": "e1",
        },
        {
            "key": "a4",
            "source": "e4",
            "relationship": "BASED_IN",
            "target": "p1",
        },
    ]
    occurrences = [
        {
            "key": f"ho{number}",
            "participants": ["e1"],
            "place": "p1",
            "world_time": number,
            "system_time": number,
            "synopsis": f"Alric event {number}.",
            "story": f"Production historical story {number}.",
            "started_associations": [],
            "ended_associations": [],
        }
        for number in range(1, 7)
    ]
    occurrences.append(
        {
            "key": "ho7",
            "participants": ["e4"],
            "place": "p1",
            "world_time": 7,
            "system_time": 7,
            "synopsis": "Guard event.",
            "story": "A Guard-only production historical story.",
            "started_associations": ["a4"],
            "ended_associations": [],
        }
    )
    occurrences[0]["place"] = "p2"
    occurrences[0]["synopsis"] = "Alric received his first Royal Guard patrol."
    occurrences[0]["story"] = "Alric's first Royal Guard patrol began at North Gate."
    return {
        "identities": identities,
        "associations": associations,
        "historical_occurrences": occurrences,
    }


def _package(tmp_path: Path) -> Path:
    memory = tmp_path / "memory.json"
    memory.write_text(json.dumps(_memory()), encoding="utf-8")
    return tmp_path


def _adapter(tmp_path: Path) -> Any:
    return adapter_module.ProductionCamAdapter(import_world(_package(tmp_path)))


def test_groq_librarian_reuses_transport_with_unchanged_cam_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        {"role": "system", "content": "unchanged contract"},
        {"role": "user", "content": "unchanged CAM packet"},
    ]
    captured: tuple[list[dict[str, str]], str] | None = None

    def fake_groq(
        supplied_messages: list[dict[str, str]], model: str
    ) -> Any:
        nonlocal captured
        captured = supplied_messages, model
        return provider_module.ProviderResult(
            "ANSWER: Directly supported.\nEVIDENCE: none",
            {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        )

    monkeypatch.setattr(question_module, "call_groq_model", fake_groq)
    provider = question_module.GroqCamNativeProvider("openai/gpt-oss-20b")

    response = provider(messages)

    assert captured == (messages, "openai/gpt-oss-20b")
    assert captured[0] is messages
    assert response.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
    }


def test_authored_world_imports_through_production_cam(tmp_path: Path) -> None:
    world = import_world(_package(tmp_path))

    assert len(world.identities.all()) == 6
    assert len(world.associations.all()) == 4
    assert len(world.occurrences.all()) == 7


def test_literal_question_activation_is_case_insensitive_whole_name_only(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)

    assert adapter.activate_question("Where were ELARA, Alric, and Dorf?") == (
        "Elara",
        "Alric",
        "Dorf",
    )
    assert adapter.activate_question("Does Al count?") == ()


def test_unknown_question_fails_cleanly_without_live_provider(tmp_path: Path) -> None:
    called = False

    def provider(_messages: list[dict[str, str]]) -> Any:
        nonlocal called
        called = True
        raise AssertionError("provider must not be called")

    result = question_module.run_world_question(
        _package(tmp_path), "Who is the stranger?", provider_fn=provider
    )

    assert result.status == "cam_initial_failure"
    assert "No literal production Identity" in result.error
    assert called is False


def test_initial_packet_is_bounded_and_neighbors_do_not_recursively_expand(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    session = adapter_module.ProductionMemorySession()

    packet = adapter.build_initial_packet("Tell me about Alric.", session)

    assert len(packet.associations) == 3
    assert len(packet.history) == 5
    assert any(item.name == "Royal Guard" for item in packet.new_synopses)
    assert all(item.relationship != "BASED_IN" for item in packet.associations)
    assert all("Guard-only" not in item.story for item in packet.history)


def test_initial_packet_budget_is_global_across_multiple_explicit_activations(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    session = adapter_module.ProductionMemorySession()

    packet = adapter.build_initial_packet(
        "What connects Alric, Dorf, the Royal Guard, and Stonebridge?", session
    )

    assert len(packet.associations) == 3
    assert len(packet.history) == 5
    assert len({item.identifier for item in packet.associations}) == 3
    assert len({item.identifier for item in packet.history}) == 5
    assert [item.identifier for item in packet.associations] == sorted(
        item.identifier for item in packet.associations
    )
    assert [item.world_time for item in packet.history] == sorted(
        (item.world_time for item in packet.history), reverse=True
    )


def test_expansion_channels_return_production_cam_records(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    session = adapter_module.ProductionMemorySession()
    opening = adapter.build_initial_packet("Tell me about Alric.", session)

    description = adapter.expand("Royal Guard", "DESCRIPTION", session)
    associations = adapter.expand("Royal Guard", "ASSOCIATIONS", session)
    history = adapter.expand("Alric", "HISTORY", session)

    assert description.full_descriptions[0].description.startswith("Royal Guard's full")
    assert associations.associations[0].identifier.startswith("A-")
    assert associations.associations[0].relationship == "BASED_IN"
    assert history.history[0].identifier.startswith("HO-")
    assert "first Royal Guard patrol began" in history.history[0].story
    assert {item.identifier for item in opening.associations}.isdisjoint(
        {item.identifier for item in associations.associations}
    )


def test_already_supplied_expansion_returns_deterministic_feedback(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    session = adapter_module.ProductionMemorySession()
    adapter.build_initial_packet("Tell me about Alric.", session)

    packet = adapter.expand("Alric", "DESCRIPTION", session)

    assert not packet.full_descriptions
    assert "already supplied" in packet.question


def test_cyclic_associations_do_not_trigger_recursive_traversal(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    session = adapter_module.ProductionMemorySession()
    packet = adapter.build_initial_packet("Tell me about Dorf.", session)

    assert len(packet.associations) <= 3
    assert len({item.identifier for item in packet.associations}) == len(
        packet.associations
    )
    assert all(item.relationship != "BASED_IN" for item in packet.associations)


def test_transcript_records_exact_messages_and_telemetry_without_changing_memory(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    original_memory = (package / "memory.json").read_bytes()
    calls: list[list[dict[str, str]]] = []
    responses = iter(
        [
            "EXPAND Royal Guard DESCRIPTION",
            "ANSWER: The Guard is described in production CAM.\nEVIDENCE: none",
        ]
    )

    def provider(messages: list[dict[str, str]]) -> Any:
        calls.append([dict(message) for message in messages])
        return provider_module.ProviderResult(
            next(responses),
            {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        )

    result = question_module.run_world_question(
        package, "Tell me about Alric.", provider_fn=provider
    )

    assert result.status == "answered"
    assert [item.sender for item in result.transcript] == [
        "CAM",
        "MINI-IGOR",
        "CAM",
        "MINI-IGOR",
    ]
    assert result.transcript[0].content == calls[0][-1]["content"]
    assert result.transcript[1].content == calls[1][-2]["content"]
    assert result.transcript[2].content == calls[1][-1]["content"]
    assert result.llm_calls == 2
    assert result.cam_expansions == 1
    assert result.cam_activation_count == 1
    assert result.provider_prompt_tokens == 20
    assert result.provider_completion_tokens == 8
    assert result.provider_total_tokens == 28
    assert result.admitted_evidence
    assert any(
        "Alric's full production Description" in item
        for item in result.admitted_descriptions
    )
    assert (package / "memory.json").read_bytes() == original_memory


def test_specific_history_is_retrieved_before_answer_when_absent_from_packet_one(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def provider(messages: list[dict[str, str]]) -> Any:
        packet = messages[-1]["content"]
        calls.append(packet)
        match = re.search(
            r"\[(HO-[0-9a-f-]+)\].*first Royal Guard patrol began at North Gate",
            packet,
        )
        if match is None:
            assert "EXPAND Alric HISTORY" in packet
            return provider_module.ProviderResult("EXPAND Alric HISTORY", {})
        return provider_module.ProviderResult(
            "ANSWER: Alric's first Royal Guard patrol began at North Gate.\n"
            f"EVIDENCE: {match.group(1)}",
            {},
        )

    result = question_module.run_world_question(
        _package(tmp_path),
        "Where did Alric's first Royal Guard patrol begin?",
        provider_fn=provider,
    )

    assert result.status == "answered"
    assert "first Royal Guard patrol began" not in calls[0]
    assert result.cam_expansions == 2
    assert result.llm_calls == 3
    assert result.evidence_ids[0] in result.admitted_evidence


def test_answer_citing_unadmitted_evidence_fails_clearly(tmp_path: Path) -> None:
    invented_id = "HO-00000000-0000-4000-8000-999999999999"

    def provider(_messages: list[dict[str, str]]) -> Any:
        return provider_module.ProviderResult(
            f"ANSWER: An unsupported historical claim.\nEVIDENCE: {invented_id}",
            {},
        )

    result = question_module.run_world_question(
        _package(tmp_path), "What happened to Alric?", provider_fn=provider
    )

    assert result.status == "evidence_failure"
    assert result.answer is None
    assert result.evidence_ids == ()
    assert result.error == (
        f"ANSWER cited evidence not admitted in this session: {invented_id}"
    )


def test_directly_supported_history_answers_without_expansion(tmp_path: Path) -> None:
    def provider(messages: list[dict[str, str]]) -> Any:
        packet = messages[-1]["content"]
        match = re.search(r"\[(HO-[0-9a-f-]+)\].*Production historical story 6", packet)
        assert match is not None
        return provider_module.ProviderResult(
            f"ANSWER: Alric event 6 occurred.\nEVIDENCE: {match.group(1)}",
            {},
        )

    result = question_module.run_world_question(
        _package(tmp_path), "What was Alric event 6?", provider_fn=provider
    )

    assert result.status == "answered"
    assert result.llm_calls == 1
    assert result.cam_expansions == 0


def test_history_retrieval_remains_bounded_by_max_rounds(tmp_path: Path) -> None:
    def provider(_messages: list[dict[str, str]]) -> Any:
        return provider_module.ProviderResult("EXPAND Alric HISTORY", {})

    result = question_module.run_world_question(
        _package(tmp_path),
        "Where did Alric's first patrol begin?",
        provider_fn=provider,
        max_rounds=1,
    )

    assert result.status == "max_rounds"
    assert result.llm_calls == 1
    assert result.cam_expansions == 1
