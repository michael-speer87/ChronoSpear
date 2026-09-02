from dataclasses import FrozenInstanceError

import pytest

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    ChronoStamp,
    HistoricalOccurrence,
    IdentityCatalog,
    IdentityId,
    IdentityKind,
    IdentityNode,
    OccurrenceCatalog,
    OccurrenceId,
    RelationshipVocabulary,
    SystemTime,
    WorldTime,
)

ALRIC = IdentityId("E-00000000-0000-4000-8000-000000000001")
ROYAL_GUARD = IdentityId("E-00000000-0000-4000-8000-000000000002")
UNKNOWN_ENTITY = IdentityId("E-00000000-0000-4000-8000-000000000099")
STONEBRIDGE = IdentityId("P-00000000-0000-4000-8000-000000000001")
UNKNOWN_PLACE = IdentityId("P-00000000-0000-4000-8000-000000000099")
FIGHTER = IdentityId("D-00000000-0000-4000-8000-000000000001")
A1 = AssociationId("A-00000000-0000-4000-8000-000000000001")
A2 = AssociationId("A-00000000-0000-4000-8000-000000000002")
UNKNOWN_ASSOCIATION = AssociationId("A-00000000-0000-4000-8000-000000000099")
O1 = "HO-00000000-0000-4000-8000-000000000001"
O2 = "HO-00000000-0000-4000-8000-000000000002"
_DEFAULT_PARTICIPANTS = (ALRIC, ROYAL_GUARD)
_DEFAULT_PLACE = STONEBRIDGE


def _nodes() -> IdentityCatalog:
    nodes = IdentityCatalog()
    nodes.add(IdentityNode(ALRIC, "Alric", IdentityKind.ENTITY))
    nodes.add(
        IdentityNode(ROYAL_GUARD, "Royal Guard", IdentityKind.ENTITY)
    )
    nodes.add(IdentityNode(STONEBRIDGE, "Stonebridge", IdentityKind.PLACE))
    nodes.add(IdentityNode(FIGHTER, "Fighter", IdentityKind.DESCRIBER))
    return nodes


def _stamp() -> ChronoStamp:
    return ChronoStamp(WorldTime(300), SystemTime(20))


def _catalog() -> OccurrenceCatalog:
    nodes = _nodes()
    vocabulary = RelationshipVocabulary.core()
    associations = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    associations.add(
        Association(
            A1,
            ALRIC,
            vocabulary.require("MEMBER_OF"),
            ROYAL_GUARD,
        )
    )
    associations.add(
        Association(
            A2,
            ROYAL_GUARD,
            vocabulary.require("BASED_IN"),
            STONEBRIDGE,
        )
    )
    return OccurrenceCatalog(nodes=nodes, associations=associations)


def _occurrence(
    occurrence_id: str = O1,
    *,
    stamp: ChronoStamp | None = None,
    synopsis: str = "Alric joined the Royal Guard.",
    story: str = "Alric formally joined the Royal Guard at Stonebridge.",
    participants: tuple[IdentityId, ...] = _DEFAULT_PARTICIPANTS,
    place: IdentityId = _DEFAULT_PLACE,
    started_associations: tuple[AssociationId, ...] = (),
    ended_associations: tuple[AssociationId, ...] = (),
) -> HistoricalOccurrence:
    return HistoricalOccurrence(
        occurrence_id=OccurrenceId(occurrence_id),
        stamp=stamp or _stamp(),
        synopsis=synopsis,
        story=story,
        participants=participants,
        place=place,
        started_associations=started_associations,
        ended_associations=ended_associations,
    )


def test_occurrence_id_rejects_blank_and_generated_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="Occurrence ID cannot be empty"):
        OccurrenceId("   ")

    assert OccurrenceId.new() != OccurrenceId.new()


def test_historical_occurrence_is_immutable() -> None:
    occurrence = _occurrence()

    with pytest.raises(FrozenInstanceError):
        occurrence.synopsis = "Changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        occurrence.started_associations = (A1,)  # type: ignore[misc]


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


def test_historical_occurrence_requires_entity_participant() -> None:
    with pytest.raises(ValueError, match="at least one Entity participant"):
        _occurrence(participants=())


def test_historical_occurrence_rejects_duplicate_participants() -> None:
    with pytest.raises(ValueError, match="participants cannot contain duplicates"):
        _occurrence(participants=(ALRIC, ALRIC))


def test_historical_occurrence_supports_multiple_started_and_ended_associations() -> None:
    started = _occurrence(started_associations=(A1, A2))
    ended = _occurrence(O2, ended_associations=(A1, A2))

    catalog = _catalog()
    assert catalog.add(started) is started
    assert catalog.add(ended) is ended


def test_historical_occurrence_rejects_duplicate_started_associations() -> None:
    with pytest.raises(ValueError, match="started Associations cannot contain duplicates"):
        _occurrence(started_associations=(A1, A1))


def test_historical_occurrence_rejects_duplicate_ended_associations() -> None:
    with pytest.raises(ValueError, match="ended Associations cannot contain duplicates"):
        _occurrence(ended_associations=(A1, A1))


def test_historical_occurrence_cannot_start_and_end_same_association() -> None:
    with pytest.raises(ValueError, match="cannot both start and end"):
        _occurrence(
            started_associations=(A1,),
            ended_associations=(A1,),
        )


def test_occurrence_catalog_rejects_unknown_started_association() -> None:
    with pytest.raises(KeyError, match="Unknown Historical Occurrence started Association"):
        _catalog().add(_occurrence(started_associations=(UNKNOWN_ASSOCIATION,)))


def test_occurrence_catalog_rejects_unknown_ended_association() -> None:
    with pytest.raises(KeyError, match="Unknown Historical Occurrence ended Association"):
        _catalog().add(_occurrence(ended_associations=(UNKNOWN_ASSOCIATION,)))


def test_occurrence_catalog_accepts_known_entity_participants_and_place() -> None:
    catalog = _catalog()
    occurrence = _occurrence()

    assert catalog.add(occurrence) is occurrence
    assert catalog.get(OccurrenceId(O1)) is occurrence


def test_occurrence_catalog_create_generates_unique_typed_ids() -> None:
    catalog = _catalog()
    first = catalog.create(
        stamp=_stamp(),
        synopsis="First event.",
        story="The first event happened.",
        participants=(ALRIC,),
        place=STONEBRIDGE,
        started_associations=(A1,),
    )
    second = catalog.create(
        stamp=_stamp(),
        synopsis="Second event.",
        story="The second event happened.",
        participants=(ALRIC,),
        place=STONEBRIDGE,
        ended_associations=(A1,),
    )

    assert first.occurrence_id.value.startswith("HO-")
    assert second.occurrence_id != first.occurrence_id


def test_occurrence_catalog_rejects_unknown_participant() -> None:
    catalog = _catalog()
    occurrence = _occurrence(participants=(UNKNOWN_ENTITY,))

    with pytest.raises(KeyError, match="Unknown Historical Occurrence participant"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_place_identity_as_participant() -> None:
    catalog = _catalog()
    occurrence = _occurrence(participants=(STONEBRIDGE,))

    with pytest.raises(ValueError, match="IdentityKind.ENTITY"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_describer_identity_as_participant() -> None:
    catalog = _catalog()
    occurrence = _occurrence(participants=(FIGHTER,))

    with pytest.raises(ValueError, match="IdentityKind.ENTITY"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_unknown_place() -> None:
    catalog = _catalog()
    occurrence = _occurrence(place=UNKNOWN_PLACE)

    with pytest.raises(KeyError, match="Unknown Historical Occurrence place"):
        catalog.add(occurrence)


def test_occurrence_catalog_rejects_non_place_identity_as_place() -> None:
    catalog = _catalog()
    occurrence = _occurrence(place=ROYAL_GUARD)

    with pytest.raises(ValueError, match="IdentityKind.PLACE"):
        catalog.add(occurrence)


def test_exact_readdition_is_idempotent() -> None:
    catalog = _catalog()
    occurrence = _occurrence()

    first = catalog.add(occurrence)
    second = catalog.add(occurrence)

    assert second is first
    assert len(catalog.all()) == 1


def test_occurrence_id_cannot_point_to_conflicting_history() -> None:
    catalog = _catalog()
    catalog.add(_occurrence())

    with pytest.raises(ValueError, match=f"Occurrence ID {O1} is already in use"):
        catalog.add(_occurrence(story="A different account of what happened."))


def test_identical_payloads_with_different_ids_can_coexist() -> None:
    catalog = _catalog()
    first = catalog.add(_occurrence(O1))
    second = catalog.add(_occurrence(O2))

    assert first.occurrence_id != second.occurrence_id
    assert len(catalog.all()) == 2


def test_distinct_occurrences_may_share_same_chronostamp() -> None:
    catalog = _catalog()
    shared_stamp = _stamp()

    first = catalog.add(_occurrence(O1, stamp=shared_stamp))
    second = catalog.add(
        _occurrence(
            O2,
            stamp=shared_stamp,
            synopsis="The town bell rang.",
            story="The Stonebridge town bell rang during Alric's induction.",
        )
    )

    assert first.stamp == second.stamp
    assert len(catalog.all()) == 2
