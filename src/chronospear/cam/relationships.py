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


class RelationshipVocabulary:
    """Small explicit registry of approved Relationship Types.

    Associations must use a RelationshipType definition approved by this vocabulary.
    New durable relationship semantics are registered intentionally by application
    code, never silently invented from arbitrary LLM text.
    """

    def __init__(self) -> None:
        self._types: dict[str, RelationshipType] = {}

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
