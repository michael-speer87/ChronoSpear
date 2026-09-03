from dataclasses import FrozenInstanceError

import pytest

from chronospear.cam import IdentityCatalog, IdentityId, IdentityKind, IdentityNode

ENTITY_1 = IdentityId("E-00000000-0000-4000-8000-000000000001")
ENTITY_2 = IdentityId("E-00000000-0000-4000-8000-000000000002")


def test_identity_node_keeps_minimal_identity_shape() -> None:
    node = IdentityNode(
        identity_id=ENTITY_1,
        name=" Alric ",
        kind=IdentityKind.ENTITY,
        description=" A veteran guard. ",
    )

    assert node.identity_id == ENTITY_1
    assert node.name == "Alric"
    assert node.kind is IdentityKind.ENTITY
    assert node.description == "A veteran guard."
    assert node.synopsis == ""


def test_identity_node_normalizes_optional_synopsis() -> None:
    node = IdentityNode(
        identity_id=ENTITY_1,
        name="Alric",
        kind=IdentityKind.ENTITY,
        description=" Full authoritative detail. ",
        synopsis=" Human fighter and veteran adventurer. ",
    )

    assert node.name == "Alric"
    assert node.synopsis == "Human fighter and veteran adventurer."
    assert node.description == "Full authoritative detail."


def test_identity_kind_contains_only_current_identity_families() -> None:
    assert set(IdentityKind) == {
        IdentityKind.ENTITY,
        IdentityKind.PLACE,
        IdentityKind.DESCRIBER,
    }


def test_identity_node_allows_empty_normalized_metadata() -> None:
    node = IdentityNode(ENTITY_1, "  ", IdentityKind.ENTITY, "  ")

    assert node.name == ""
    assert node.description == ""


def test_identity_node_is_immutable() -> None:
    node = IdentityNode(ENTITY_1, "Alric", IdentityKind.ENTITY)

    with pytest.raises(FrozenInstanceError):
        setattr(node, "name", "Someone Else")  # noqa: B010


def test_identity_catalog_rejects_conflicting_identity_id() -> None:
    catalog = IdentityCatalog()
    catalog.add(IdentityNode(ENTITY_1, "Alric", IdentityKind.ENTITY))

    with pytest.raises(ValueError, match="already in use"):
        catalog.add(IdentityNode(ENTITY_1, "Elara", IdentityKind.ENTITY))


def test_identity_catalog_accepts_idempotent_readd() -> None:
    catalog = IdentityCatalog()
    node = IdentityNode(ENTITY_1, "Alric", IdentityKind.ENTITY)

    assert catalog.add(node) is node
    assert catalog.add(node) == node
    assert catalog.all() == (node,)


@pytest.mark.parametrize(
    ("identity_id", "kind"),
    [
        ("P-00000000-0000-4000-8000-000000000001", IdentityKind.ENTITY),
        ("D-00000000-0000-4000-8000-000000000001", IdentityKind.PLACE),
        ("E-00000000-0000-4000-8000-000000000001", IdentityKind.DESCRIBER),
    ],
)
def test_identity_prefix_must_agree_with_kind(identity_id: str, kind: IdentityKind) -> None:
    with pytest.raises(ValueError, match="prefix must agree"):
        IdentityNode(IdentityId(identity_id), "", kind)


def test_identity_catalog_create_generates_kind_specific_unique_ids() -> None:
    catalog = IdentityCatalog()
    entity = catalog.create(kind=IdentityKind.ENTITY, name="Alric")
    other_entity = catalog.create(kind=IdentityKind.ENTITY)
    place = catalog.create(kind=IdentityKind.PLACE, name="Stonebridge")
    describer = catalog.create(kind=IdentityKind.DESCRIBER, name="Fighter")

    assert entity.identity_id.value.startswith("E-")
    assert other_entity.identity_id != entity.identity_id
    assert place.identity_id.value.startswith("P-")
    assert describer.identity_id.value.startswith("D-")
    assert catalog.all() == (entity, other_entity, place, describer)


def test_identity_catalog_create_accepts_synopsis_without_affecting_id_type() -> None:
    node = IdentityCatalog().create(
        kind=IdentityKind.ENTITY,
        name="Alric",
        synopsis="Human fighter.",
        description="Full authoritative detail.",
    )

    assert node.identity_id.value.startswith("E-")
    assert node.synopsis == "Human fighter."
