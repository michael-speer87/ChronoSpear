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

ENTITY_1 = IdentityId("E-00000000-0000-4000-8000-000000000001")
ENTITY_2 = IdentityId("E-00000000-0000-4000-8000-000000000002")
UNKNOWN = IdentityId("E-00000000-0000-4000-8000-000000000099")
A1 = AssociationId("A-00000000-0000-4000-8000-000000000001")
A2 = AssociationId("A-00000000-0000-4000-8000-000000000002")


def _fixture() -> tuple[IdentityCatalog, RelationshipVocabulary, RelationshipType]:
    nodes = IdentityCatalog()
    nodes.add(IdentityNode(ENTITY_1, "Alric", IdentityKind.ENTITY))
    nodes.add(
        IdentityNode(ENTITY_2, "Royal Guard", IdentityKind.ENTITY)
    )
    relationships = RelationshipVocabulary()
    member_of = relationships.register(RelationshipType("MEMBER_OF"))
    return nodes, relationships, member_of


def test_association_preserves_directionality() -> None:
    _, _, member_of = _fixture()
    association = Association(
        A1,
        ENTITY_1,
        member_of,
        ENTITY_2,
    )

    assert association.source == ENTITY_1
    assert association.target == ENTITY_2


def test_different_relationships_can_connect_same_nodes() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    first = catalog.add(
        Association(
            A1,
            ENTITY_1,
            member_of,
            ENTITY_2,
        )
    )
    second = catalog.add(
        Association(
            A2,
            ENTITY_1,
            opposes,
            ENTITY_2,
        )
    )

    assert first.semantic_key != second.semantic_key
    assert len(catalog.all()) == 2


def test_association_catalog_create_generates_unique_typed_ids_and_deduplicates() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    first = catalog.create(source=ENTITY_1, relationship=member_of, target=ENTITY_2)
    duplicate = catalog.create(source=ENTITY_1, relationship=member_of, target=ENTITY_2)
    second = catalog.create(source=ENTITY_1, relationship=opposes, target=ENTITY_2)

    assert first.association_id.value.startswith("A-")
    assert duplicate is first
    assert second.association_id != first.association_id


def test_association_catalog_rejects_unknown_source() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown source Identity"):
        catalog.add(
            Association(
                A1,
                UNKNOWN,
                member_of,
                ENTITY_2,
            )
        )


def test_association_catalog_rejects_unknown_target() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown target Identity"):
        catalog.add(
            Association(
                A1,
                ENTITY_1,
                member_of,
                UNKNOWN,
            )
        )


def test_association_catalog_rejects_unapproved_relationship() -> None:
    nodes, vocabulary, _ = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(ValueError, match="not approved"):
        catalog.add(
            Association(
                A1,
                ENTITY_1,
                RelationshipType("INVENTED_BY_MODEL"),
                ENTITY_2,
            )
        )


def test_semantic_duplicate_returns_existing_association() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    first = catalog.add(
        Association(
            A1,
            ENTITY_1,
            member_of,
            ENTITY_2,
        )
    )

    duplicate = catalog.add(
        Association(
            A2,
            ENTITY_1,
            member_of,
            ENTITY_2,
        )
    )

    assert duplicate is first
    assert len(catalog.all()) == 1


def test_association_id_cannot_point_to_conflicting_assertions() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    catalog.add(
        Association(
            A1,
            ENTITY_1,
            member_of,
            ENTITY_2,
        )
    )

    with pytest.raises(ValueError, match="already in use"):
        catalog.add(
            Association(
                A1,
                ENTITY_1,
                opposes,
                ENTITY_2,
            )
        )
