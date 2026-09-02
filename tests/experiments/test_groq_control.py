from chronospear.experiments.groq_control import (
    build_control_scenario,
    build_decoy_expansion_control_scenario,
    build_expansion_control_scenario,
    build_redhaven_replication_scenario,
)
from chronospear.experiments.natural_language_cam import (
    NaturalLanguageProviderRequest,
    NaturalLanguageProviderResponse,
    run_natural_language_experiment,
)


def test_control_scenario_has_sufficient_initial_and_irrelevant_expansions() -> None:
    scenario = build_control_scenario()
    rendered = "\n".join(scenario.initial_evidence.records)

    assert "--BASED_IN-->" in rendered
    assert "Archivist Sol" in rendered
    assert "Lumenport" in rendered
    assert scenario.expansion_selectors == ("node:stonebridge", "association:A2")
    assert "stonebridge" not in rendered
    assert "brass_compass" not in rendered


def test_expansion_control_moves_only_necessary_fact_out_of_initial_evidence() -> None:
    experiment_one = build_control_scenario()
    experiment_two = build_expansion_control_scenario()

    assert experiment_two.action == experiment_one.action
    assert experiment_two.initial_evidence == experiment_one.initial_evidence.records[:-1]
    assert "archivist_sol --BASED_IN--> lumenport" not in "\n".join(
        experiment_two.initial_evidence
    )


def test_expansion_control_relevant_fact_is_derivable_only_after_expansion() -> None:
    scenario = build_expansion_control_scenario()
    resolution = scenario.resolver.resolve(
        "Where is Archivist Sol based?",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )

    assert resolution.activations == ("Archivist Sol location",)
    assert resolution.added_evidence == (
        "Archivist Sol --BASED_IN--> Lumenport",
    )
    combined = scenario.initial_evidence + resolution.added_evidence
    assert "Archivist Sol --BASED_IN--> Lumenport" in "\n".join(combined)


def test_expansion_control_keeps_an_irrelevant_valid_choice() -> None:
    scenario = build_expansion_control_scenario()
    resolution = scenario.resolver.resolve(
        "What equipment does Nera carry?",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )

    assert resolution.activations == ("Nera equipment",)
    assert resolution.added_evidence == ("Nera --OWNS--> Brass Compass",)
    assert "Lumenport" not in resolution.added_evidence[0]


def test_experiment_two_b_changes_only_initial_evidence_from_two_a() -> None:
    experiment_two_a = build_expansion_control_scenario()
    experiment_two_b = build_decoy_expansion_control_scenario()

    assert experiment_two_b.action == experiment_two_a.action
    assert experiment_two_b.initial_evidence[:3] == experiment_two_a.initial_evidence
    assert experiment_two_b.initial_evidence[3:] == (
        "NODE stonebridge | PLACE | Stonebridge | A city beside an old stone crossing.",
        "NODE redhaven | PLACE | Redhaven | A walled city with red-roofed markets.",
        "NODE willowmere | PLACE | Willowmere | A lakeside city bordered by willow groves.",
    )


def test_experiment_two_b_retains_same_hidden_location_answer() -> None:
    scenario = build_decoy_expansion_control_scenario()
    resolution = scenario.resolver.resolve(
        "Where is Archivist Sol located?",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )

    assert resolution.activations == ("Archivist Sol location",)
    assert resolution.added_evidence == (
        "Archivist Sol --BASED_IN--> Lumenport",
    )


def test_experiment_two_a_remains_the_original_three_record_fixture() -> None:
    scenario = build_expansion_control_scenario()

    assert scenario.initial_evidence == (
        "NODE E-00000000-0000-4000-8000-000000000001 | "
        "ENTITY | Nera | A trusted courier.",
        "NODE E-00000000-0000-4000-8000-000000000002 | "
        "ENTITY | Archivist Sol | A keeper of civic records.",
        (
            "NODE P-00000000-0000-4000-8000-000000000001 | PLACE | Lumenport | "
            "A harbor city known for its beacon towers."
        ),
    )


def test_experiment_two_c_has_reordered_plausible_places_without_relationship() -> None:
    experiment_two_b = build_decoy_expansion_control_scenario()
    experiment_two_c = build_redhaven_replication_scenario()
    place_records = experiment_two_c.initial_evidence[2:]

    assert len(place_records) == 4
    assert tuple(record.split(" | ")[2] for record in place_records) == (
        "Willowmere",
        "Lumenport",
        "Redhaven",
        "Stonebridge",
    )
    assert place_records != experiment_two_b.initial_evidence[2:]
    assert all("BASED_IN" not in record for record in experiment_two_c.initial_evidence)


def test_experiment_two_c_location_activation_returns_hidden_redhaven_fact() -> None:
    scenario = build_redhaven_replication_scenario()
    resolution = scenario.resolver.resolve(
        "I need to know where Archivist Sol is based.",
        seen_evidence=frozenset(scenario.initial_evidence),
        remaining_records=8,
        remaining_utf8_bytes=2_000,
    )

    assert resolution.activations == ("Archivist Sol location",)
    assert resolution.added_evidence == (
        "Archivist Sol --BASED_IN--> Redhaven",
    )


def test_experiment_two_c_prompt_hides_internal_ids_and_selectors() -> None:
    scenario = build_redhaven_replication_scenario()
    requests: list[NaturalLanguageProviderRequest] = []

    def provider(
        request: NaturalLanguageProviderRequest,
    ) -> NaturalLanguageProviderResponse:
        requests.append(request)
        return NaturalLanguageProviderResponse("Redhaven")

    run_natural_language_experiment(
        action=scenario.action,
        initial_evidence=scenario.initial_evidence,
        resolver=scenario.resolver,
        provider=provider,
    )
    prompt = "\n".join(message.content for message in requests[0].messages)

    assert "NODE " not in prompt
    assert "archivist_sol" not in prompt
    assert "association:" not in prompt
    assert "node:" not in prompt


def test_experiment_two_c_conclusion_support_follows_redhaven_evidence() -> None:
    scenario = build_redhaven_replication_scenario()
    responses = iter(
        ("Where is Archivist Sol based?", "Nera should travel to Redhaven.")
    )

    def provider(
        request: NaturalLanguageProviderRequest,
    ) -> NaturalLanguageProviderResponse:
        return NaturalLanguageProviderResponse(next(responses))

    report = run_natural_language_experiment(
        action=scenario.action,
        initial_evidence=scenario.initial_evidence,
        resolver=scenario.resolver,
        provider=provider,
    )

    assert report.final_conclusion == "Nera should travel to Redhaven."
    assert report.conclusion_supported is True


def test_experiment_two_b_remains_the_original_six_record_fixture() -> None:
    scenario = build_decoy_expansion_control_scenario()

    assert tuple(record.split(" | ")[2] for record in scenario.initial_evidence[2:]) == (
        "Lumenport",
        "Stonebridge",
        "Redhaven",
        "Willowmere",
    )
