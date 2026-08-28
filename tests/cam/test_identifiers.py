import pytest

from chronospear.cam import AssociationId, NodeId


def test_node_id_rejects_blank() -> None:
    with pytest.raises(ValueError, match="Node ID cannot be empty"):
        NodeId("  ")


def test_association_id_rejects_blank() -> None:
    with pytest.raises(ValueError, match="Association ID cannot be empty"):
        AssociationId("")


def test_generated_node_ids_are_unique() -> None:
    assert NodeId.new() != NodeId.new()


def test_generated_association_ids_are_unique() -> None:
    assert AssociationId.new() != AssociationId.new()
