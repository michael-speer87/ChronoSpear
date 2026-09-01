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


def _fixture() -> tuple[IdentityCatalog, RelationshipVocabulary, RelationshipType]:
    nodes = IdentityCatalog()
    nodes.add(IdentityNode(IdentityId("alric"), "Alric", IdentityKind.ENTITY))
    nodes.add(
        IdentityNode(IdentityId("royal_guard"), "Royal Guard", IdentityKind.ENTITY)
    )
    relationships = RelationshipVocabulary()
    member_of = relationships.register(RelationshipType("MEMBER_OF"))
    return nodes, relationships, member_of


def test_association_preserves_directionality() -> None:
    _, _, member_of = _fixture()
    association = Association(
        AssociationId("A1"),
        IdentityId("alric"),
        member_of,
        IdentityId("royal_guard"),
    )

    assert association.source == IdentityId("alric")
    assert association.target == IdentityId("royal_guard")


def test_different_relationships_can_connect_same_nodes() -> None:
    nodes, vocabulary, member_of = _fixture()
    opposes = vocabulary.register(RelationshipType("OPPOSES"))
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    first = catalog.add(
        Association(
            AssociationId("A1"),
            IdentityId("alric"),
            member_of,
            IdentityId("royal_guard"),
        )
    )
    second = catalog.add(
        Association(
            AssociationId("A2"),
            IdentityId("alric"),
            opposes,
            IdentityId("royal_guard"),
        )
    )

    assert first.semantic_key != second.semantic_key
    assert len(catalog.all()) == 2


def test_association_catalog_rejects_unknown_source() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown source Identity"):
        catalog.add(
            Association(
                AssociationId("A1"),
                IdentityId("unknown"),
                member_of,
                IdentityId("royal_guard"),
            )
        )


def test_association_catalog_rejects_unknown_target() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(KeyError, match="Unknown target Identity"):
        catalog.add(
            Association(
                AssociationId("A1"),
                IdentityId("alric"),
                member_of,
                IdentityId("unknown"),
            )
        )


def test_association_catalog_rejects_unapproved_relationship() -> None:
    nodes, vocabulary, _ = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)

    with pytest.raises(ValueError, match="not approved"):
        catalog.add(
            Association(
                AssociationId("A1"),
                IdentityId("alric"),
                RelationshipType("INVENTED_BY_MODEL"),
                IdentityId("royal_guard"),
            )
        )


def test_semantic_duplicate_returns_existing_association() -> None:
    nodes, vocabulary, member_of = _fixture()
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    first = catalog.add(
        Association(
            AssociationId("A1"),
            IdentityId("alric"),
            member_of,
            IdentityId("royal_guard"),
        )
    )

    duplicate = catalog.add(
        Association(
            AssociationId("A2"),
            IdentityId("alric"),
            member_of,
            IdentityId("royal_guard"),
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
            AssociationId("A1"),
            IdentityId("alric"),
            member_of,
            IdentityId("royal_guard"),
        )
    )

    with pytest.raises(ValueError, match="already in use"):
        catalog.add(
            Association(
                AssociationId("A1"),
                IdentityId("alric"),
                opposes,
                IdentityId("royal_guard"),
            )
        )
