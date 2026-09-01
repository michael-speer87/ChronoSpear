import pytest

from chronospear.cam import (
    CORE_RELATIONSHIP_TYPES,
    RelationshipType,
    RelationshipVocabulary,
)


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


def test_plain_vocabulary_requires_intentional_registration() -> None:
    vocabulary = RelationshipVocabulary()

    with pytest.raises(KeyError, match="Unknown Relationship Type"):
        vocabulary.require("MEMBER_OF")


def test_core_vocabulary_contains_only_locked_core_relationships() -> None:
    vocabulary = RelationshipVocabulary.core()

    assert tuple(relationship.name for relationship in CORE_RELATIONSHIP_TYPES) == (
        "IS_A",
        "MEMBER_OF",
        "PART_OF",
        "LOCATED_IN",
        "BASED_IN",
        "OWNS",
        "OPPOSES",
    )
    assert vocabulary.all() == CORE_RELATIONSHIP_TYPES
    assert vocabulary.require("IS_A") is CORE_RELATIONSHIP_TYPES[0]


def test_core_vocabulary_does_not_include_perspective_or_domain_relationships() -> None:
    vocabulary = RelationshipVocabulary.core()

    for name in ("KNOWS", "FRIEND_OF", "PARENT_OF", "ATTACKS"):
        with pytest.raises(KeyError, match="Unknown Relationship Type"):
            vocabulary.require(name)


def test_core_vocabulary_instances_are_independent() -> None:
    first = RelationshipVocabulary.core()
    second = RelationshipVocabulary.core()
    custom = first.register(RelationshipType("CUSTOM_RELATION"))

    assert first.require("CUSTOM_RELATION") is custom
    with pytest.raises(KeyError, match="Unknown Relationship Type"):
        second.require("CUSTOM_RELATION")


def test_vocabulary_returns_registered_relationship() -> None:
    vocabulary = RelationshipVocabulary()
    member_of = vocabulary.register(RelationshipType("MEMBER_OF"))

    assert vocabulary.require("MEMBER_OF") is member_of


def test_vocabulary_rejects_conflicting_definition() -> None:
    vocabulary = RelationshipVocabulary()
    vocabulary.register(RelationshipType("MEMBER_OF", "Membership."))

    with pytest.raises(ValueError, match="different definition"):
        vocabulary.register(RelationshipType("MEMBER_OF", "Something else."))
