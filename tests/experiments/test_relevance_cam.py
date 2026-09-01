from collections.abc import Iterable

from chronospear.experiments.groq_control import (
    build_decoy_expansion_control_scenario,
    build_expansion_control_scenario,
    build_redhaven_replication_scenario,
)
from chronospear.experiments.natural_language_cam import (
    NaturalLanguageProviderRequest,
    NaturalLanguageProviderResponse,
)
from chronospear.experiments.relevance_cam import (
    EXPERIMENT_3_ACTION,
    RelevanceLimits,
    build_relevance_world,
    prepare_relevance_experiment,
    run_relevance_experiment,
)


class ScriptedProvider:
    def __init__(self, responses: Iterable[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[NaturalLanguageProviderRequest] = []

    def __call__(
        self, request: NaturalLanguageProviderRequest
    ) -> NaturalLanguageProviderResponse:
        self.requests.append(request)
        return NaturalLanguageProviderResponse(
            raw_text=next(self._responses),
            input_tokens=20,
            output_tokens=5,
            model="fake-model",
            provider_latency_seconds=0.01,
            wall_latency_seconds=0.02,
        )


def test_full_fixture_is_substantially_larger_than_initial_relevance_packet() -> None:
    scenario = prepare_relevance_experiment()

    assert scenario.fixture_metrics.identity_nodes >= 10
    assert scenario.fixture_metrics.associations >= 10
    assert scenario.fixture_metrics.evidence_records >= 20
    assert scenario.initial_recall.records_selected == 2
    assert scenario.fixture_metrics.evidence_records >= (
        10 * scenario.initial_recall.records_selected
    )


def test_initial_recall_selects_action_anchors_without_places_or_associations() -> None:
    scenario = prepare_relevance_experiment()

    assert scenario.initial_recall.action_anchors == ("Nera", "Archivist Sol")
    assert scenario.initial_recall.semantic_families_considered == ("IDENTITY",)
    assert scenario.initial_evidence == (
        "ENTITY | Nera | A trusted courier.",
        "ENTITY | Archivist Sol | A keeper of civic records.",
    )
    assert all("PLACE" not in record for record in scenario.initial_evidence)
    assert all("--" not in record for record in scenario.initial_evidence)
    assert "BASED_IN" not in "\n".join(scenario.initial_evidence)


def test_location_language_activates_target_then_bounded_cam_neighborhood() -> None:
    scenario = prepare_relevance_experiment()
    resolution = scenario.resolver.resolve(
        "I need to know which city Archivist Sol is located in.",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )
    trace = scenario.resolver.traces[-1]

    assert resolution.activations == ("Archivist Sol location",)
    assert trace.cam_targets == (
        "Identity Archivist Sol / relationship family BASED_IN",
    )
    assert trace.candidate_records_examined == 4
    assert resolution.added_evidence == (
        "Archivist Sol --BASED_IN--> Redhaven",
    )
    assert trace.records_rejected == 3
    assert "MEMBER_OF" not in "\n".join(resolution.added_evidence)


def test_repeated_location_request_suppresses_duplicate_evidence() -> None:
    scenario = prepare_relevance_experiment()
    first = scenario.resolver.resolve(
        "Where is Archivist Sol based?",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )
    second = scenario.resolver.resolve(
        "Where is Archivist Sol located?",
        seen_evidence=frozenset(scenario.initial_evidence + first.added_evidence),
        remaining_records=7,
        remaining_utf8_bytes=1_900,
    )

    assert second.added_evidence == ()
    assert scenario.resolver.traces[-1].duplicate_records_suppressed == 1


def test_recall_and_expansion_budgets_are_hard_limits() -> None:
    scenario = prepare_relevance_experiment(
        RelevanceLimits(
            max_initial_records=1,
            max_initial_utf8_bytes=1_000,
            max_expansion_candidates=2,
            max_expansion_records=1,
        )
    )
    resolution = scenario.resolver.resolve(
        "Where is Archivist Sol based?",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )

    assert scenario.initial_recall.records_selected == 1
    assert scenario.initial_recall.records_rejected >= 1
    assert scenario.resolver.traces[-1].candidate_records_examined == 2
    assert resolution.added_evidence == ()


def test_complete_cam_and_llm_taxation_is_retained() -> None:
    provider = ScriptedProvider(
        (
            "I need to know where Archivist Sol is based.",
            "Redhaven.",
        )
    )

    report = run_relevance_experiment(provider=provider)

    assert report.llm.provider_calls == 2
    assert report.llm.expansion_rounds == 1
    assert report.expansions[0].raw_context_request == (
        "I need to know where Archivist Sol is based."
    )
    assert report.expansions[0].records_returned == (
        "Archivist Sol --BASED_IN--> Redhaven",
    )
    assert report.total_cam_candidates_examined == (
        report.initial_recall.candidate_records_examined
        + report.expansions[0].candidate_records_examined
    )
    assert report.total_cam_records_exposed == 3
    assert report.exposed_fixture_fraction == (
        report.total_cam_records_exposed / report.fixture.evidence_records
    )
    assert report.llm.total_input_tokens == 40
    assert report.llm.total_output_tokens == 10
    assert report.llm.final_conclusion == "Redhaven."
    assert report.llm.conclusion_supported is True
    assert report.llm.calls[1].interpretation == "conclusion"
    assert len(provider.requests) == 2


def test_llm_messages_hide_ids_selectors_and_unrelated_fixture_evidence() -> None:
    provider = ScriptedProvider(("Nera should travel to Redhaven.",))
    report = run_relevance_experiment(provider=provider)
    prompt = "\n".join(message.content for message in provider.requests[0].messages)

    assert report.llm.conclusion_supported is False
    assert "NODE " not in prompt
    assert "assoc" not in prompt.casefold()
    assert "node:" not in prompt
    assert "Silver Key" not in prompt
    assert "Ashen Circle" not in prompt
    assert "Redhaven" not in prompt


def test_relevance_experiment_does_not_mutate_world_fixture() -> None:
    world = build_relevance_world()
    identities_before = world.identities
    associations_before = world.associations
    provider = ScriptedProvider(("Nera should travel to Redhaven.",))

    run_relevance_experiment(provider=provider, world=world)

    assert world.identities == identities_before
    assert world.associations == associations_before


def test_experiments_two_a_two_b_and_two_c_remain_unchanged() -> None:
    two_a = build_expansion_control_scenario()
    two_b = build_decoy_expansion_control_scenario()
    two_c = build_redhaven_replication_scenario()

    assert two_a.initial_evidence == two_b.initial_evidence[:3]
    assert tuple(record.split(" | ")[2] for record in two_b.initial_evidence[2:]) == (
        "Lumenport",
        "Stonebridge",
        "Redhaven",
        "Willowmere",
    )
    assert tuple(record.split(" | ")[2] for record in two_c.initial_evidence[2:]) == (
        "Willowmere",
        "Lumenport",
        "Redhaven",
        "Stonebridge",
    )
    assert two_a.action == EXPERIMENT_3_ACTION
