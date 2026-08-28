import pytest

from chronospear.cam import RelationshipType, RelationshipVocabulary


def test_relationship_type_requires_canonical_name() -> None:
    relationship = RelationshipType("MEMBER_OF", "Membership in an organization.")

    assert relationship.name == "MEMBER_OF"


@pytest.mark.parametrize("bad_name", ["member_of", "member of", "", "_MEMBER_OF"])
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
