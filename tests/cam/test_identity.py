from dataclasses import FrozenInstanceError

import pytest

from chronospear.cam import IdentityCatalog, IdentityId, IdentityKind, IdentityNode


def test_identity_node_keeps_minimal_identity_shape() -> None:
    node = IdentityNode(
        identity_id=IdentityId("alric"),
        name=" Alric ",
        kind=IdentityKind.ENTITY,
        description=" A veteran guard. ",
    )

    assert node.identity_id == IdentityId("alric")
    assert node.name == "Alric"
    assert node.kind is IdentityKind.ENTITY
    assert node.description == "A veteran guard."


def test_identity_kind_contains_only_current_identity_families() -> None:
    assert set(IdentityKind) == {
        IdentityKind.ENTITY,
        IdentityKind.PLACE,
        IdentityKind.DESCRIBER,
    }


def test_identity_node_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        IdentityNode(IdentityId("x"), "  ", IdentityKind.ENTITY)


def test_identity_node_is_immutable() -> None:
    node = IdentityNode(IdentityId("alric"), "Alric", IdentityKind.ENTITY)

    with pytest.raises(FrozenInstanceError):
        setattr(node, "name", "Someone Else")  # noqa: B010


def test_identity_catalog_rejects_conflicting_identity_id() -> None:
    catalog = IdentityCatalog()
    catalog.add(IdentityNode(IdentityId("same"), "Alric", IdentityKind.ENTITY))

    with pytest.raises(ValueError, match="already in use"):
        catalog.add(IdentityNode(IdentityId("same"), "Elara", IdentityKind.ENTITY))


def test_identity_catalog_accepts_idempotent_readd() -> None:
    catalog = IdentityCatalog()
    node = IdentityNode(IdentityId("alric"), "Alric", IdentityKind.ENTITY)

    assert catalog.add(node) is node
    assert catalog.add(node) == node
    assert catalog.all() == (node,)
