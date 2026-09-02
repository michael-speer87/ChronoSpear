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
        IdentityNode(IdentityId("alric"), "Alric", IdentityKind.ENTITY, "A knight."),
        IdentityNode(IdentityId("elara"), "Elara", IdentityKind.ENTITY, "A traveler."),
        IdentityNode(
            IdentityId("royal_guard"),
            "Royal Guard",
            IdentityKind.ENTITY,
            "The kingdom's royal guard.",
        ),
        IdentityNode(
            IdentityId("stonebridge"),
            "Stonebridge",
            IdentityKind.PLACE,
            "A fortified bridge settlement.",
        ),
        IdentityNode(
            IdentityId("fighter"),
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
            AssociationId("alric_member_of_royal_guard"),
            IdentityId("alric"),
            vocabulary.require("MEMBER_OF"),
            IdentityId("royal_guard"),
        ),
        Association(
            AssociationId("royal_guard_based_in_stonebridge"),
            IdentityId("royal_guard"),
            vocabulary.require("BASED_IN"),
            IdentityId("stonebridge"),
        ),
        Association(
            AssociationId("alric_is_a_fighter"),
            IdentityId("alric"),
            vocabulary.require("IS_A"),
            IdentityId("fighter"),
        ),
    ):
        associations.add(association)

    occurrences = OccurrenceCatalog(nodes=identities)
    occurrences.add(
        HistoricalOccurrence(
            OccurrenceId("alric_joins_guard"),
            ChronoStamp(WorldTime(10), SystemTime(1)),
            "Alric joined the Royal Guard at Stonebridge.",
            "Alric swore his oath and joined the Royal Guard at Stonebridge.",
            (IdentityId("alric"),),
            IdentityId("stonebridge"),
        )
    )
    occurrences.add(
        HistoricalOccurrence(
            OccurrenceId("alric_leaves_guard"),
            ChronoStamp(WorldTime(20), SystemTime(2)),
            "Alric left the Royal Guard at Stonebridge.",
            "Alric ended his service with the Royal Guard at Stonebridge.",
            (IdentityId("alric"),),
            IdentityId("stonebridge"),
        )
    )
    return DemoWorld(identities, associations, occurrences)
