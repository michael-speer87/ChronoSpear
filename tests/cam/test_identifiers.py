from uuid import UUID

import pytest

from chronospear.cam import AssociationId, IdentityId, OccurrenceId


@pytest.mark.parametrize(
    ("value", "identifier_type", "message"),
    [
        ("  ", IdentityId, "Identity ID cannot be empty"),
        ("", AssociationId, "Association ID cannot be empty"),
        ("not-an-id", OccurrenceId, "Occurrence ID must use"),
        (
            "A-00000000-0000-4000-8000-000000000001",
            IdentityId,
            "Identity ID must use",
        ),
        (
            "E-00000000-0000-4000-8000-000000000001",
            AssociationId,
            "Association ID must use",
        ),
        ("E-not-a-uuid", IdentityId, "valid UUID4"),
        (
            "A-00000000-0000-1000-8000-000000000001",
            AssociationId,
            "canonical lowercase UUID4",
        ),
    ],
)
def test_identifiers_reject_invalid_values(
    value: str,
    identifier_type: type[IdentityId] | type[AssociationId] | type[OccurrenceId],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        identifier_type(value)


@pytest.mark.parametrize(
    "value",
    [
        "E-00000000-0000-4000-8000-000000000001",
        "P-00000000-0000-4000-8000-000000000001",
        "D-00000000-0000-4000-8000-000000000001",
        "A-00000000-0000-4000-8000-000000000001",
        "HO-00000000-0000-4000-8000-000000000001",
    ],
)
def test_valid_typed_uuid4_fixtures_are_accepted(value: str) -> None:
    if value.startswith("HO-"):
        assert str(OccurrenceId(value)) == value
    elif value.startswith("A-"):
        assert str(AssociationId(value)) == value
    else:
        assert str(IdentityId(value)) == value


def test_generated_identifiers_are_real_unique_uuid4_values() -> None:
    identifiers: list[IdentityId | AssociationId | OccurrenceId] = [
        IdentityId.new("E"),
        IdentityId.new("E"),
        IdentityId.new("P"),
        IdentityId.new("D"),
        AssociationId.new(),
        AssociationId.new(),
        OccurrenceId.new(),
        OccurrenceId.new(),
    ]

    assert len({identifier.value for identifier in identifiers}) == len(identifiers)
    for identifier in identifiers:
        uuid_text = identifier.value.split("-", maxsplit=1)[1]
        assert UUID(uuid_text).version == 4
