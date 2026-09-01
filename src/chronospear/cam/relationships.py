from __future__ import annotations

import re
from dataclasses import dataclass

_RELATIONSHIP_NAME = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class RelationshipType:
    """One intentionally approved semantic relationship in CAM's vocabulary.

    Relationship Types are controlled vocabulary, not Identity Nodes.
    """

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not _RELATIONSHIP_NAME.fullmatch(name):
            raise ValueError(
                "Relationship Type names must use canonical UPPER_SNAKE_CASE."
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", self.description.strip())

    def __str__(self) -> str:
        return self.name


CORE_RELATIONSHIP_TYPES: tuple[RelationshipType, ...] = (
    RelationshipType("IS_A", "Classifies an Identity using a Describer."),
    RelationshipType("MEMBER_OF", "Connects an Entity to an organization or group."),
    RelationshipType("PART_OF", "Connects an Identity to a larger containing Identity."),
    RelationshipType("LOCATED_IN", "Connects an Entity to a contextually relevant Place."),
    RelationshipType("BASED_IN", "Connects an Entity to its base or headquarters Place."),
    RelationshipType("OWNS", "Connects an Entity to another Entity it owns."),
    RelationshipType("OPPOSES", "Connects an Entity to another Entity it actively opposes."),
)


class RelationshipVocabulary:
    """Small explicit registry of approved Relationship Types.

    Associations must use a RelationshipType definition approved by this vocabulary.
    ChronoSpear defines a small stable core, while additional durable relationship
    semantics are still registered intentionally by application code and are never
    silently invented from arbitrary LLM text.
    """

    def __init__(self) -> None:
        self._types: dict[str, RelationshipType] = {}

    @classmethod
    def core(cls) -> RelationshipVocabulary:
        """Return a fresh vocabulary containing only ChronoSpear's locked core."""

        vocabulary = cls()
        for relationship in CORE_RELATIONSHIP_TYPES:
            vocabulary.register(relationship)
        return vocabulary

    def register(self, relationship: RelationshipType) -> RelationshipType:
        existing = self._types.get(relationship.name)
        if existing is None:
            self._types[relationship.name] = relationship
            return relationship
        if existing == relationship:
            return existing
        raise ValueError(
            f"Relationship Type {relationship.name!r} is already registered "
            "with a different definition."
        )

    def require(self, name: str) -> RelationshipType:
        canonical = name.strip()
        try:
            return self._types[canonical]
        except KeyError as exc:
            raise KeyError(f"Unknown Relationship Type: {canonical!r}.") from exc

    def contains(self, relationship: RelationshipType) -> bool:
        return self._types.get(relationship.name) == relationship

    def all(self) -> tuple[RelationshipType, ...]:
        return tuple(self._types.values())
