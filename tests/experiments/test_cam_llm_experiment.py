from collections.abc import Iterable
from dataclasses import FrozenInstanceError

import pytest

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    IdentityCatalog,
    IdentityId,
    IdentityKind,
    IdentityNode,
    RelationshipType,
    RelationshipVocabulary,
)
from chronospear.experiments.cam_llm import (
    EvidenceBundle,
    ExperimentLimits,
    ExperimentProtocolError,
    ProviderRequest,
    ProviderResponse,
    WhitelistExpansionResolver,
    run_action_experiment,
)


class ScriptedProvider:
    def __init__(self, responses: Iterable[ProviderResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[ProviderRequest] = []

    def __call__(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return next(self._responses)


def _cam_fixture() -> tuple[EvidenceBundle, WhitelistExpansionResolver]:
    nodes = IdentityCatalog()
    alric = nodes.add(
        IdentityNode(
            IdentityId("E-00000000-0000-4000-8000-000000000001"),
            "Alric",
            IdentityKind.ENTITY,
        )
    )
    guard = nodes.add(
        IdentityNode(
            IdentityId("E-00000000-0000-4000-8000-000000000002"),
            "Royal Guard",
            IdentityKind.ENTITY,
        )
    )
    bridge = nodes.add(
        IdentityNode(
            IdentityId("P-00000000-0000-4000-8000-000000000001"),
            "Stonebridge",
            IdentityKind.PLACE,
        )
    )

    vocabulary = RelationshipVocabulary()
    member_of = vocabulary.register(RelationshipType("MEMBER_OF"))
    based_in = vocabulary.register(RelationshipType("BASED_IN"))
    associations = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    membership = associations.add(
        Association(
            AssociationId("A-00000000-0000-4000-8000-000000000001"),
            alric.identity_id,
            member_of,
            guard.identity_id,
        )
    )
    headquarters = associations.add(
        Association(
            AssociationId("A-00000000-0000-4000-8000-000000000002"),
            guard.identity_id,
            based_in,
            bridge.identity_id,
        )
    )

    initial = EvidenceBundle(
        "initial",
        (
            (
                f"NODE {alric.identity_id} | {alric.kind} | "
                f"{alric.name} | {alric.description}"
            ),
            (
                f"NODE {guard.identity_id} | {guard.kind} | "
                f"{guard.name} | {guard.description}"
            ),
            (
                f"ASSOC {membership.association_id} | {membership.source} "
                f"--{membership.relationship}--> {membership.target}"
            ),
        ),
    )
    resolver = WhitelistExpansionResolver(
        {
            "node:stonebridge": EvidenceBundle(
                "node:stonebridge",
                (
                    f"NODE {bridge.identity_id} | {bridge.kind} | "
                    f"{bridge.name} | {bridge.description}",
                ),
            ),
            "association:A2": EvidenceBundle(
                "association:A2",
                (
                    (
                        f"ASSOC {headquarters.association_id} | {headquarters.source} "
                        f"--{headquarters.relationship}--> {headquarters.target}"
                    ),
                ),
            ),
            "duplicate:membership": EvidenceBundle(
                "duplicate:membership",
                (initial.records[-1],),
            ),
        }
    )
    return initial, resolver


def test_initial_context_can_produce_a_conclusion_without_expansion() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [ProviderResponse.conclusion("Alric serves the Royal Guard.", 41, 9)]
    )

    report = run_action_experiment(
        action="Who does Alric serve?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    assert report.provider_calls == 1
    assert report.expansion_requests == ()
    assert report.final_conclusion == "Alric serves the Royal Guard."
    assert report.initial_context.record_count == 3
    assert report.initial_context.characters == len("\n".join(initial.records))
    assert report.initial_context.utf8_bytes == len("\n".join(initial.records).encode())
    assert report.total_input_tokens == 41
    assert report.total_output_tokens == 9


def test_valid_expansion_adds_only_whitelisted_evidence_and_records_metrics() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [
            ProviderResponse.expansion(
                ("association:A2",), "Need the guard's base.", 50, 12
            ),
            ProviderResponse.conclusion("The trail leads to Stonebridge.", 71, 8),
        ]
    )

    report = run_action_experiment(
        action="Where should Alric report?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    expansion = report.expansion_requests[0]
    assert report.provider_calls == 2
    assert expansion.selectors == ("association:A2",)
    assert expansion.granted == ("association:A2",)
    assert expansion.rejected == ()
    assert expansion.added_context.record_count == 1
    assert provider.requests[0].evidence == initial.records
    assert provider.requests[1].evidence == initial.records + (
        "ASSOC A-00000000-0000-4000-8000-000000000002 | "
        "E-00000000-0000-4000-8000-000000000002 --BASED_IN--> "
        "P-00000000-0000-4000-8000-000000000001",
    )
    assert report.calls[0].context == report.initial_context
    assert report.calls[1].context.record_count == 4
    assert report.calls[1].context.characters == len(
        "\n".join(provider.requests[1].evidence)
    )
    assert report.calls[1].context.utf8_bytes == len(
        "\n".join(provider.requests[1].evidence).encode("utf-8")
    )
    assert report.total_input_tokens == 121
    assert report.total_output_tokens == 20


def test_unknown_and_duplicate_selectors_never_add_evidence() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [
            ProviderResponse.expansion(
                ("unknown:secret", "duplicate:membership"), "Looking for more.", 20, 5
            ),
            ProviderResponse.conclusion("No further supported conclusion.", 22, 6),
        ]
    )

    report = run_action_experiment(
        action="What else is known?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    expansion = report.expansion_requests[0]
    assert expansion.granted == ()
    assert expansion.rejected == (
        "unknown:secret: not whitelisted",
        "duplicate:membership: no new evidence",
    )
    assert provider.requests[1].evidence == initial.records


def test_selector_record_and_byte_limits_are_hard_limits() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [
            ProviderResponse.expansion(
                ("node:stonebridge", "association:A2"), "Need both.", 20, 5
            ),
            ProviderResponse.conclusion("Only bounded evidence was considered.", 25, 7),
        ]
    )
    limits = ExperimentLimits(
        max_expansion_rounds=1,
        max_selectors_per_request=1,
        max_added_records=1,
        max_added_utf8_bytes=1,
    )

    report = run_action_experiment(
        action="Where is the guard?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
        limits=limits,
    )

    expansion = report.expansion_requests[0]
    assert expansion.granted == ()
    assert expansion.rejected == (
        "association:A2: selector limit exceeded",
        "node:stonebridge: evidence budget exceeded",
    )
    assert provider.requests[1].evidence == initial.records


def test_provider_must_conclude_after_expansion_round_limit() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [
            ProviderResponse.expansion(("association:A2",), "Need context.", 10, 3),
            ProviderResponse.expansion(("node:stonebridge",), "Need more.", 15, 3),
        ]
    )

    with pytest.raises(ExperimentProtocolError, match="expansion round limit"):
        run_action_experiment(
            action="Where should Alric report?",
            initial_evidence=initial,
            resolver=resolver,
            provider=provider,
            limits=ExperimentLimits(max_expansion_rounds=1),
        )

    assert len(provider.requests) == 2


def test_multiple_expansion_rounds_share_one_cumulative_budget() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [
            ProviderResponse.expansion(("association:A2",), "Need the base.", 10, 3),
            ProviderResponse.expansion(("node:stonebridge",), "Need the place.", 15, 3),
            ProviderResponse.conclusion("The guard is based in Stonebridge.", 20, 6),
        ]
    )

    report = run_action_experiment(
        action="Where is the Royal Guard based?",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
        limits=ExperimentLimits(max_added_records=2),
    )

    assert tuple(item.granted for item in report.expansion_requests) == (
        ("association:A2",),
        ("node:stonebridge",),
    )
    assert report.calls[-1].context.record_count == 5
    assert report.provider_calls == 3


def test_conclusion_must_obey_compactness_limit() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider([ProviderResponse.conclusion("Too long.", 10, 2)])

    with pytest.raises(ExperimentProtocolError, match="compactness limit"):
        run_action_experiment(
            action="Conclude compactly.",
            initial_evidence=initial,
            resolver=resolver,
            provider=provider,
            limits=ExperimentLimits(max_conclusion_characters=4),
        )


def test_missing_usage_is_unavailable_instead_of_zero() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider(
        [ProviderResponse.conclusion("A compact answer.", None, None)]
    )

    report = run_action_experiment(
        action="Answer compactly.",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    assert report.calls[0].input_tokens is None
    assert report.calls[0].output_tokens is None
    assert report.total_input_tokens is None
    assert report.total_output_tokens is None


def test_report_is_immutable_and_cam_catalogs_are_not_mutated() -> None:
    initial, resolver = _cam_fixture()
    provider = ScriptedProvider([ProviderResponse.conclusion("Done.", 10, 2)])

    report = run_action_experiment(
        action="Conclude.",
        initial_evidence=initial,
        resolver=resolver,
        provider=provider,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(report, "final_conclusion", "Changed.")  # noqa: B010


def test_each_run_starts_with_only_its_own_initial_evidence() -> None:
    initial, resolver = _cam_fixture()
    first = ScriptedProvider([ProviderResponse.conclusion("First.", 10, 2)])
    second = ScriptedProvider([ProviderResponse.conclusion("Second.", 11, 2)])

    run_action_experiment("First action.", initial, resolver, first)
    run_action_experiment("Second action.", initial, resolver, second)

    assert first.requests == [ProviderRequest("First action.", initial.records, 1)]
    assert second.requests == [ProviderRequest("Second action.", initial.records, 1)]


def test_malformed_provider_response_is_rejected() -> None:
    with pytest.raises(ValueError, match="conclusion text"):
        ProviderResponse(kind="conclusion", text="", input_tokens=1, output_tokens=1)
