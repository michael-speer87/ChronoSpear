from dataclasses import FrozenInstanceError

import pytest

from chronospear.cam import (
    ChronoStamp,
    HistoricalOccurrence,
    IdentityCatalog,
    IdentityId,
    IdentityKind,
    IdentityNode,
    OccurrenceCatalog,
    OccurrenceId,
    SystemTime,
    WorldTime,
)

_DEFAULT_PARTICIPANTS = (IdentityId("alric"), IdentityId("royal_guard"))
_DEFAULT_PLACE = IdentityId("stonebridge")


def _nodes() -> IdentityCatalog:
    nodes = IdentityCatalog()
    nodes.add(IdentityNode(IdentityId("alric"), "Alric", IdentityKind.ENTITY))
    nodes.add(
        IdentityNode(IdentityId("royal_guard"), "Royal Guard", IdentityKind.ENTITY)
    )
    nodes.add(IdentityNode(IdentityId("stonebridge"), "Stonebridge", IdentityKind.PLACE))
    return nodes


def _stamp() -> ChronoStamp:
    return ChronoStamp(WorldTime(300), SystemTime(20))


def _occurrence(
    occurrence_id: str = "O1",
    *,
    stamp: ChronoStamp | None = None,
    synopsis: str = "Alric joined the Royal Guard.",
    story: str = "Alric formally joined the Royal Guard at Stonebridge.",
    participants: tuple[IdentityId, ...] = _DEFAULT_PARTICIPANTS,
    place: IdentityId | None = _DEFAULT_PLACE,
) -> HistoricalOccurrence:
    return HistoricalOccurrence(
        occurrence_id=OccurrenceId(occurrence_id),
        stamp=stamp or _stamp(),
        synopsis=synopsis,
        story=story,
        participants=participants,
        place=place,
    )


def test_occurrence_id_rejects_blank_and_generated_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="Occurrence ID cannot be empty"):
        OccurrenceId("   ")

    assert OccurrenceId.new() != OccurrenceId.new()


def test_historical_occurrence_is_immutable() -> None:
    occurrence = _occurrence()

    with pytest.raises(FrozenInstanceError):
        occurrence.synopsis = "Changed"  # type: ignore[misc]


def test_historical_occurrence_normalizes_synopsis_and_story() -> None:
    occurrence = _occurrence(
        synopsis="  Alric joined the Royal Guard.  ",
        story="  Alric formally joined the Royal Guard.  ",
    )

    assert occurrence.synopsis == "Alric joined the Royal Guard."
    assert occurrence.story == "Alric formally joined the Royal Guard."


def test_historical_occurrence_rejects_blank_synopsis() -> None:
    with pytest.raises(ValueError, match="Historical Occurrence synopsis cannot be empty"):
        _occurrence(synopsis="   ")


def test_historical_occurrence_rejects_blank_story() -> None:
    with pytest.raises(ValueError, match="Historical Occurrence story cannot be empty"):
        _occurrence(story="   ")


def test_historical_occurrence_rejects_duplicate_participants() -> None:
    with pytest.raises(ValueError, match="participants cannot contain duplicates"):
        _occurrence(
            participants=(IdentityId("alric"), IdentityId("alric")),
            place=None,
        )


def test_historical_occurrence_requires_graph_anchor() -> None:
    with pytest.raises(ValueError, match="at least one participant or place"):
        _occurrence(participants=(), place=None)


def test_occurrence_catalog_accepts_known_participants_and_place() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    occurrence = _occurrence()

    assert catalog.add(occurrence) is occurrence
    assert catalog.get(OccurrenceId("O1")) is occurrence


def test_occurrence_catalog_rejects_unknown_participant() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    occurrence = _occurrence(
        participants=(IdentityId("unknown"),),
        place=None,
    )

    with pytest.raises(KeyError, match="Unknown Historical Occurrence participant"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_unknown_place() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    occurrence = _occurrence(place=IdentityId("unknown_place"))

    with pytest.raises(KeyError, match="Unknown Historical Occurrence place"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_non_place_identity_as_place() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    occurrence = _occurrence(place=IdentityId("royal_guard"))

    with pytest.raises(ValueError, match="IdentityKind.PLACE"):
        catalog.add(occurrence)


def test_exact_readdition_is_idempotent() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    occurrence = _occurrence()

    first = catalog.add(occurrence)
    second = catalog.add(occurrence)

    assert second is first
    assert len(catalog.all()) == 1


def test_occurrence_id_cannot_point_to_conflicting_history() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    catalog.add(_occurrence())

    with pytest.raises(ValueError, match="Occurrence ID O1 is already in use"):
        catalog.add(_occurrence(story="A different account of what happened."))


def test_identical_payloads_with_different_ids_can_coexist() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    first = catalog.add(_occurrence("O1"))
    second = catalog.add(_occurrence("O2"))

    assert first.occurrence_id != second.occurrence_id
    assert len(catalog.all()) == 2


def test_distinct_occurrences_may_share_same_chronostamp() -> None:
    catalog = OccurrenceCatalog(nodes=_nodes())
    shared_stamp = _stamp()

    first = catalog.add(_occurrence("O1", stamp=shared_stamp))
    second = catalog.add(
        _occurrence(
            "O2",
            stamp=shared_stamp,
            synopsis="The town bell rang.",
            story="The Stonebridge town bell rang during Alric's induction.",
        )
    )

    assert first.stamp == second.stamp
    assert len(catalog.all()) == 2
