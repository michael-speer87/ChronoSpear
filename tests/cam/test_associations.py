import pytest

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    IdentityCatalog,
    IdentityKind,
    IdentityNode,
    NodeId,
    RelationshipType,
    RelationshipVocabulary,
)


def _fixture() -> tuple[IdentityCatalog, RelationshipVocabulary, RelationshipType]:
    nodes = IdentityCatalog()
    nodes.add(IdentityNode(NodeId("alric"), "Alric", IdentityKind.ENTITY))
    nodes.add(IdentityNode(NodeId("royal_guard"), "Royal Guard", IdentityKind.ENTITY))
    relationships = RelationshipVocabulary()
    member_of = relationships.register(RelationshipType("MEMBER_OF"))
    return nodes, relationships, member_of


def test_association_preserves_directionality() -> None:
    _, _, member_of = _fixture()
    association = Association(
        AssociationId("A1"),
        NodeId("alric"),
        member_of,
        NodeId("royal_guard"),
    )

    assert association.source == NodeId("alric")
    assert association.target == NodeId("royal_guard")


def test_different_relationships_can_connect_same_nodes() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    first = catalog.add(
        Association(AssociationId("A1"), NodeId("alric"), member_of, NodeId("royal_guard"))
    )
    second = catalog.add(
        Association(AssociationId("A2"), NodeId("alric"), opposes, NodeId("royal_guard"))
    )

    assert first.semantic_key != second.semantic_key
    assert len(catalog.all()) == 2


def test_association_catalog_rejects_unknown_source() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown source Node"):
        catalog.add(
            Association(
                AssociationId("A1"),
                NodeId("unknown"),
                member_of,
                NodeId("royal_guard"),
            )
        )


def test_association_catalog_rejects_unknown_target() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown target Node"):
        catalog.add(
            Association(
                AssociationId("A1"),
                NodeId("alric"),
                member_of,
                NodeId("unknown"),
            )
        )


def test_association_catalog_rejects_unapproved_relationship() -> None:
    nodes, vocabulary, _ = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(ValueError, match="not approved"):
        catalog.add(
            Association(
                AssociationId("A1"),
                NodeId("alric"),
                RelationshipType("INVENTED_BY_MODEL"),
                NodeId("royal_guard"),
            )
        )


def test_semantic_duplicate_returns_existing_association() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    first = catalog.add(
        Association(AssociationId("A1"), NodeId("alric"), member_of, NodeId("royal_guard"))
    )

    duplicate = catalog.add(
        Association(AssociationId("A2"), NodeId("alric"), member_of, NodeId("royal_guard"))
    )

    assert duplicate is first
    assert len(catalog.all()) == 1


def test_association_id_cannot_point_to_conflicting_assertions() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    catalog.add(
        Association(AssociationId("A1"), NodeId("alric"), member_of, NodeId("royal_guard"))
    )

    with pytest.raises(ValueError, match="already in use"):
        catalog.add(
            Association(AssociationId("A1"), NodeId("alric"), opposes, NodeId("royal_guard"))
        )
