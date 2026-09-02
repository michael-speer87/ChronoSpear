from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4


def _validated_identifier(value: str, label: str, prefixes: tuple[str, ...]) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    prefix = next((item for item in prefixes if normalized.startswith(item)), None)
    if prefix is None:
        expected = ", ".join(prefixes)
        raise ValueError(f"{label} must use one of these prefixes: {expected}.")
    uuid_text = normalized[len(prefix) :]
    try:
        parsed = UUID(uuid_text)
    except ValueError as exc:
        raise ValueError(f"{label} must contain a valid UUID4.") from exc
    if parsed.version != 4 or str(parsed) != uuid_text:
        raise ValueError(f"{label} must contain a canonical lowercase UUID4.")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class IdentityId:
    """Stable identifier for an Identity Node.

    Other graph-addressable families receive their own identifier types. Do not
    reuse IdentityId as a universal graph ID.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validated_identifier(self.value, "Identity ID", ("E-", "P-", "D-")),
        )

    @classmethod
    def new(cls, prefix: Literal["E", "P", "D"]) -> IdentityId:
        return cls(f"{prefix}-{uuid4()}")

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
            _validated_identifier(self.value, "Association ID", ("A-",)),
        )

    @classmethod
    def new(cls) -> AssociationId:
        return cls(f"A-{uuid4()}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class OccurrenceId:
    """Stable identifier for an immutable Historical Occurrence."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validated_identifier(self.value, "Occurrence ID", ("HO-",)),
        )

    @classmethod
    def new(cls) -> OccurrenceId:
        return cls(f"HO-{uuid4()}")

    def __str__(self) -> str:
        return self.value
