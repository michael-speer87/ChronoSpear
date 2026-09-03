"""Logical authoring objects independent of any storage layout."""

from __future__ import annotations

from dataclasses import dataclass, field

from chronospear.cam import IdentityKind


@dataclass(slots=True)
class IdentityDraft:
    key: str
    kind: IdentityKind
    name: str
    synopsis: str = ""
    description: str = ""


@dataclass(slots=True)
class AssociationDraft:
    key: str
    source: str
    relationship: str
    target: str


@dataclass(slots=True)
class HistoricalOccurrenceDraft:
    key: str
    participants: list[str]
    place: str
    world_time: int
    system_time: int
    synopsis: str
    story: str
    started_associations: list[str] = field(default_factory=list)
    ended_associations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuthoringWorld:
    """Storage-agnostic collection edited by World Builder clients."""

    identities: list[IdentityDraft] = field(default_factory=list)
    associations: list[AssociationDraft] = field(default_factory=list)
    historical_occurrences: list[HistoricalOccurrenceDraft] = field(default_factory=list)

    def suggest_key(self, family: str) -> str:
        """Return the lowest unused conventional positive-number key."""

        prefixes = {
            "ENTITY": "e",
            "PLACE": "p",
            "DESCRIBER": "d",
            "association": "a",
            "historical_occurrence": "ho",
        }
        try:
            prefix = prefixes[family]
        except KeyError as exc:
            raise ValueError(f"Unknown authoring family: {family!r}.") from exc
        if family in {"ENTITY", "PLACE", "DESCRIBER"}:
            used = {item.key for item in self.identities}
        elif family == "association":
            used = {item.key for item in self.associations}
        else:
            used = {item.key for item in self.historical_occurrences}
        number = 1
        while f"{prefix}{number}" in used:
            number += 1
        return f"{prefix}{number}"
