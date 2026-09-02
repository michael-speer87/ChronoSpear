"""Deterministic CAM demo world used by the visual playground."""

from __future__ import annotations

from dataclasses import dataclass

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

ALRIC_ID = IdentityId("E-00000000-0000-4000-8000-000000000001")
ELARA_ID = IdentityId("E-00000000-0000-4000-8000-000000000002")
ROYAL_GUARD_ID = IdentityId("E-00000000-0000-4000-8000-000000000003")
STONEBRIDGE_ID = IdentityId("P-00000000-0000-4000-8000-000000000001")
FIGHTER_ID = IdentityId("D-00000000-0000-4000-8000-000000000001")
MEMBER_OF_ID = AssociationId("A-00000000-0000-4000-8000-000000000001")
BASED_IN_ID = AssociationId("A-00000000-0000-4000-8000-000000000002")
IS_A_ID = AssociationId("A-00000000-0000-4000-8000-000000000003")
JOINED_ID = OccurrenceId("HO-00000000-0000-4000-8000-000000000001")
LEFT_ID = OccurrenceId("HO-00000000-0000-4000-8000-000000000002")


@dataclass(frozen=True, slots=True)
class DemoWorld:
    """The production CAM catalogs that make up the playground fixture."""

    identities: IdentityCatalog
    associations: AssociationCatalog
    occurrences: OccurrenceCatalog


def build_demo_world() -> DemoWorld:
    """Build a small deterministic world entirely from production CAM objects."""

    identities = IdentityCatalog()
    nodes = (
        IdentityNode(ALRIC_ID, "Alric", IdentityKind.ENTITY, "A knight."),
        IdentityNode(ELARA_ID, "Elara", IdentityKind.ENTITY, "A traveler."),
        IdentityNode(
            ROYAL_GUARD_ID,
            "Royal Guard",
            IdentityKind.ENTITY,
            "The kingdom's royal guard.",
        ),
        IdentityNode(
            STONEBRIDGE_ID,
            "Stonebridge",
            IdentityKind.PLACE,
            "A fortified bridge settlement.",
        ),
        IdentityNode(
            FIGHTER_ID,
            "Fighter",
            IdentityKind.DESCRIBER,
            "A martial combatant.",
        ),
    )
    for node in nodes:
        identities.add(node)

    vocabulary = RelationshipVocabulary.core()
    associations = AssociationCatalog(nodes=identities, vocabulary=vocabulary)
    for association in (
        Association(
            MEMBER_OF_ID,
            ALRIC_ID,
            vocabulary.require("MEMBER_OF"),
            ROYAL_GUARD_ID,
        ),
        Association(
            BASED_IN_ID,
            ROYAL_GUARD_ID,
            vocabulary.require("BASED_IN"),
            STONEBRIDGE_ID,
        ),
        Association(
            IS_A_ID,
            ALRIC_ID,
            vocabulary.require("IS_A"),
            FIGHTER_ID,
        ),
    ):
        associations.add(association)

    occurrences = OccurrenceCatalog(nodes=identities, associations=associations)
    occurrences.add(
        HistoricalOccurrence(
            JOINED_ID,
            ChronoStamp(WorldTime(10), SystemTime(1)),
            "Alric joined the Royal Guard at Stonebridge.",
            "Alric swore his oath and joined the Royal Guard at Stonebridge.",
            (ALRIC_ID,),
            STONEBRIDGE_ID,
            started_associations=(MEMBER_OF_ID,),
        )
    )
    occurrences.add(
        HistoricalOccurrence(
            LEFT_ID,
            ChronoStamp(WorldTime(20), SystemTime(2)),
            "Alric left the Royal Guard at Stonebridge.",
            "Alric ended his service with the Royal Guard at Stonebridge.",
            (ALRIC_ID,),
            STONEBRIDGE_ID,
            ended_associations=(MEMBER_OF_ID,),
        )
    )
    return DemoWorld(identities, associations, occurrences)
