from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    ChronoStamp,
    HistoricalOccurrence,
    IdentityCatalog,
    IdentityKind,
    IdentityNode,
    NodeId,
    OccurrenceCatalog,
    OccurrenceId,
    RelationshipType,
    RelationshipVocabulary,
    SystemTime,
    WorldTime,
)


def test_public_cam_api_is_importable() -> None:
    assert all(
        item is not None
        for item in (
            Association,
            AssociationCatalog,
            AssociationId,
            ChronoStamp,
            HistoricalOccurrence,
            IdentityCatalog,
            IdentityKind,
            IdentityNode,
            NodeId,
            OccurrenceCatalog,
            OccurrenceId,
            RelationshipType,
            RelationshipVocabulary,
            SystemTime,
            WorldTime,
        )
    )
