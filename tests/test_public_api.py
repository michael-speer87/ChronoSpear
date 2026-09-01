from chronospear.cam import (
    CORE_RELATIONSHIP_TYPES,
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
            CORE_RELATIONSHIP_TYPES,
            ChronoStamp,
            HistoricalOccurrence,
            IdentityCatalog,
            IdentityId,
            IdentityKind,
            IdentityNode,
            OccurrenceCatalog,
            OccurrenceId,
            RelationshipType,
            RelationshipVocabulary,
            SystemTime,
            WorldTime,
        )
    )
