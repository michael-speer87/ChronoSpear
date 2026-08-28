from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


def _validated_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class NodeId:
    """Stable identifier for an Identity Node.

    Other graph-addressable families will receive their own identifier types when
    those families are implemented. Do not reuse NodeId as a universal graph ID.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validated_identifier(self.value, "Node ID"))

    @classmethod
    def new(cls) -> "NodeId":
        return cls(f"node_{uuid4().hex}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class AssociationId:
    """Stable identifier for an addressable Association assertion."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validated_identifier(self.value, "Association ID"),
        )

    @classmethod
    def new(cls) -> "AssociationId":
        return cls(f"assoc_{uuid4().hex}")

    def __str__(self) -> str:
        return self.value
