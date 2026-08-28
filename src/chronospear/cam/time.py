from __future__ import annotations

from dataclasses import dataclass
from typing import Self


def _validate_coordinate(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer coordinate.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")


@dataclass(frozen=True, slots=True, order=True)
class WorldTime:
    """Coordinate for when something happens/applies in the represented world."""

    value: int = 0

    def __post_init__(self) -> None:
        _validate_coordinate(self.value, "WorldTime")

    def advance(self, amount: int = 1) -> Self:
        _validate_coordinate(amount, "WorldTime advance amount")
        if amount == 0:
            raise ValueError("WorldTime advance amount must be greater than zero.")
        return type(self)(self.value + amount)


@dataclass(frozen=True, slots=True, order=True)
class SystemTime:
    """Monotonic coordinate for when ChronoSpear learned/accepted information."""

    value: int = 0

    def __post_init__(self) -> None:
        _validate_coordinate(self.value, "SystemTime")

    def advance(self, amount: int = 1) -> Self:
        _validate_coordinate(amount, "SystemTime advance amount")
        if amount == 0:
            raise ValueError("SystemTime advance amount must be greater than zero.")
        return type(self)(self.value + amount)


@dataclass(frozen=True, slots=True)
class ChronoStamp:
    """Immutable captured temporal coordinate: WorldTime + SystemTime.

    A ChronoStamp is not a clock and does not own 'current time'. It captures the
    authoritative WT/ST coordinates supplied by their clock owners at a boundary.
    Future Historical Occurrences can contain/reference a ChronoStamp without
    inventing their own ambiguous integer tick fields.
    """

    world_time: WorldTime
    system_time: SystemTime
