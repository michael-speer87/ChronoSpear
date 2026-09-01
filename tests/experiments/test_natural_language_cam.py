from collections.abc import Iterable

import pytest

from chronospear.experiments.cam_llm import ExperimentLimits, ExperimentProtocolError
from chronospear.experiments.natural_language_cam import (
    NaturalExperimentReport,
    NaturalLanguageProviderRequest,
    NaturalLanguageProviderResponse,
    NaturalLanguageResolver,
    run_natural_language_experiment,
)


class ScriptedNaturalProvider:
    def __init__(self, responses: Iterable[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[NaturalLanguageProviderRequest] = []

    def __call__(
        self, request: NaturalLanguageProviderRequest
    ) -> NaturalLanguageProviderResponse:
        self.requests.append(request)
        return NaturalLanguageProviderResponse(
            raw_text=next(self._responses),
            input_tokens=10,
            output_tokens=4,
            model="fake-model",
            provider_latency_seconds=0.01,
            wall_latency_seconds=0.02,
        )


def _fixture() -> tuple[tuple[str, ...], NaturalLanguageResolver]:
    initial = (
        "NODE nera | ENTITY | Nera | A trusted courier.",
        "NODE archivist_sol | ENTITY | Archivist Sol | A keeper of civic records.",
        (
            "NODE lumenport | PLACE | Lumenport | "
            "A harbor city known for its beacon towers."
        ),
    )
    resolver = NaturalLanguageResolver(
        location_evidence=("Archivist Sol --BASED_IN--> Lumenport",),
        equipment_evidence=("Nera --OWNS--> Brass Compass",),
    )
    return initial, resolver


def _run(*responses: str) -> tuple[NaturalExperimentReport, ScriptedNaturalProvider]:
    initial, resolver = _fixture()
    provider = ScriptedNaturalProvider(responses)
    report = run_natural_language_experiment(
        action=(
            "Nera must deliver a sealed dispatch directly to Archivist Sol. "
            "Which city should Nera travel to?"
        ),
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )
    return report, provider


def test_immediate_conclusion_is_recorded_as_unsupported_without_location_fact() -> None:
    report, _ = _run("Lumenport")

    assert report.final_conclusion == "Lumenport"
    assert report.conclusion_supported is False
    assert report.calls[0].interpretation == "conclusion"


def test_immediate_conclusion_is_supported_when_location_fact_is_initial() -> None:
    initial, resolver = _fixture()
    provider = ScriptedNaturalProvider(("Lumenport",))

    report = run_natural_language_experiment(
        action="Which city should Nera travel to?",
        initial_evidence=initial + ("Archivist Sol --BASED_IN--> Lumenport",),
        resolver=resolver,
        provider=provider,
    )

    assert report.final_conclusion == "Lumenport"
    assert report.conclusion_supported is True


def test_natural_location_request_resolves_hidden_based_in_evidence() -> None:
    report, _ = _run(
        "Where is Archivist Sol based?",
        "Nera should travel to Lumenport.",
    )

    first = report.calls[0]
    assert first.interpretation == "context_request"
    assert first.context_request == "Where is Archivist Sol based?"
    assert first.activations == ("Archivist Sol location",)
    assert first.added_evidence == ("Archivist Sol --BASED_IN--> Lumenport",)
    assert report.conclusion_supported is True


@pytest.mark.parametrize("destination", ["Redhaven", "Willowmere"])
def test_bare_destination_conclusion_follows_exposed_based_in_target(
    destination: str,
) -> None:
    initial = (
        "NODE nera | ENTITY | Nera | A trusted courier.",
        "NODE archivist_sol | ENTITY | Archivist Sol | A keeper of civic records.",
    )
    resolver = NaturalLanguageResolver(
        location_evidence=(f"Archivist Sol --BASED_IN--> {destination}",),
        equipment_evidence=("Nera --OWNS--> Brass Compass",),
    )
    provider = ScriptedNaturalProvider(
        ("Where is Archivist Sol located?", f"{destination}.")
    )

    report = run_natural_language_experiment(
        action=(
            "Nera must deliver a sealed dispatch directly to Archivist Sol. "
            "Which city should Nera travel to?"
        ),
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    assert report.provider_calls == 2
    assert report.calls[1].raw_response == f"{destination}."
    assert report.calls[1].interpretation == "conclusion"
    assert report.final_conclusion == f"{destination}."
    assert report.conclusion_supported is True
    assert len(provider.requests) == 2


def test_irrelevant_request_can_be_reformulated_to_retrieve_useful_evidence() -> None:
    report, _ = _run(
        "What equipment does Nera carry?",
        "I need more information about Archivist Sol's location.",
        "Lumenport",
    )

    assert report.calls[0].activations == ("Nera equipment",)
    assert report.calls[0].added_evidence == ("Nera --OWNS--> Brass Compass",)
    assert report.calls[1].activations == ("Archivist Sol location",)
    assert report.calls[1].added_evidence == (
        "Archivist Sol --BASED_IN--> Lumenport",
    )
    assert report.context_requests == (
        "What equipment does Nera carry?",
        "I need more information about Archivist Sol's location.",
    )
    assert report.conclusion_supported is True


def test_duplicate_request_does_not_add_evidence_twice() -> None:
    report, _ = _run(
        "Where is Archivist Sol located?",
        "Where is Archivist Sol based?",
        "Lumenport",
    )

    assert report.calls[0].added_evidence == (
        "Archivist Sol --BASED_IN--> Lumenport",
    )
    assert report.calls[1].activations == ("Archivist Sol location",)
    assert report.calls[1].added_evidence == ()


def test_unrecognized_request_can_continue_until_hard_call_limit() -> None:
    report, provider = _run(
        "I remain uncertain.",
        "Still uncertain.",
        "No conclusion.",
    )

    assert report.provider_calls == 3
    assert report.expansion_rounds == 2
    assert report.final_conclusion is None
    assert all(call.interpretation == "unrecognized" for call in report.calls)
    assert len(provider.requests) == 3


def test_evidence_byte_limit_prevents_oversized_expansion() -> None:
    initial, resolver = _fixture()
    provider = ScriptedNaturalProvider(
        ("Where is Archivist Sol based?", "Lumenport")
    )

    report = run_natural_language_experiment(
        action="Which city should Nera travel to?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
        limits=ExperimentLimits(max_added_utf8_bytes=1),
    )

    assert report.calls[0].activations == ("Archivist Sol location",)
    assert report.calls[0].added_evidence == ()
    assert report.conclusion_supported is False


def test_conclusion_length_limit_is_enforced() -> None:
    initial, resolver = _fixture()
    provider = ScriptedNaturalProvider(("Lumenport is the destination.",))

    with pytest.raises(ExperimentProtocolError, match="compactness limit"):
        run_natural_language_experiment(
            action="Which city should Nera travel to?",
            initial_evidence=initial,
            resolver=resolver,
            provider=provider,
            limits=ExperimentLimits(max_conclusion_characters=4),
        )


def test_prompt_messages_never_expose_internal_ids_or_selectors() -> None:
    _, provider = _run(
        "Where is Archivist Sol based?",
        "Lumenport",
    )

    rendered = "\n".join(
        message.content
        for request in provider.requests
        for message in request.messages
    )
    assert "association:A1" not in rendered
    assert "node:stonebridge" not in rendered
    assert "archivist_sol" not in rendered
    assert "NODE nera" not in rendered


def test_telemetry_records_complete_conversational_sequence() -> None:
    report, provider = _run(
        "What equipment does Nera carry?",
        "Where is Archivist Sol located?",
        "Nera should travel to Lumenport.",
    )

    assert tuple(call.raw_response for call in report.calls) == (
        "What equipment does Nera carry?",
        "Where is Archivist Sol located?",
        "Nera should travel to Lumenport.",
    )
    assert tuple(call.evidence_before for call in report.calls) == tuple(
        request.evidence for request in provider.requests
    )
    assert report.total_input_tokens == 30
    assert report.total_output_tokens == 12
    assert report.total_provider_latency_seconds == 0.03
    assert report.total_wall_latency_seconds == 0.06


def test_experiment_does_not_mutate_fixture_evidence() -> None:
    initial, resolver = _fixture()
    original = initial
    provider = ScriptedNaturalProvider(
        ("Where is Archivist Sol based?", "Lumenport")
    )

    run_natural_language_experiment(
        action="Which city should Nera travel to?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    assert initial == original
