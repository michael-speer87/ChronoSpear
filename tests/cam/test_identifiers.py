import pytest

from chronospear.cam import AssociationId, IdentityId


def test_identity_id_rejects_blank() -> None:
    with pytest.raises(ValueError, match="Identity ID cannot be empty"):
        IdentityId("  ")


def test_association_id_rejects_blank() -> None:
    with pytest.raises(ValueError, match="Association ID cannot be empty"):
        AssociationId("")


def test_generated_identity_ids_are_unique() -> None:
    assert IdentityId.new() != IdentityId.new()


def test_generated_association_ids_are_unique() -> None:
    assert AssociationId.new() != AssociationId.new()
