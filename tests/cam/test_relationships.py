import pytest

from chronospear.cam import RelationshipType, RelationshipVocabulary


def test_relationship_type_requires_canonical_name() -> None:
    relationship = RelationshipType("MEMBER_OF", "Membership in an organization.")

    assert relationship.name == "MEMBER_OF"


@pytest.mark.parametrize(
    "good_name",
    ["IS_A", "MEMBER_OF", "KNOWS_PERSON", "A", "A1"],
)
def test_relationship_type_accepts_canonical_names(good_name: str) -> None:
    assert RelationshipType(good_name).name == good_name


@pytest.mark.parametrize(
    "bad_name",
    ["A_", "A__B", "_A", "member_of", "member of", ""],
)
def test_relationship_type_rejects_noncanonical_names(bad_name: str) -> None:
    with pytest.raises(ValueError, match="UPPER_SNAKE_CASE"):
        RelationshipType(bad_name)


def test_vocabulary_requires_intentional_registration() -> None:
    vocabulary = RelationshipVocabulary()

    with pytest.raises(KeyError, match="Unknown Relationship Type"):
        vocabulary.require("MEMBER_OF")


def test_vocabulary_returns_registered_relationship() -> None:
    vocabulary = RelationshipVocabulary()
    member_of = vocabulary.register(RelationshipType("MEMBER_OF"))

    assert vocabulary.require("MEMBER_OF") is member_of


def test_vocabulary_rejects_conflicting_definition() -> None:
    vocabulary = RelationshipVocabulary()
    vocabulary.register(RelationshipType("MEMBER_OF", "Membership."))

    with pytest.raises(ValueError, match="different definition"):
        vocabulary.register(RelationshipType("MEMBER_OF", "Something else."))
