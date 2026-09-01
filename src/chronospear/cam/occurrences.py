from __future__ import annotations

from dataclasses import dataclass

from chronospear.cam.catalog import IdentityCatalog
from chronospear.cam.identifiers import NodeId, OccurrenceId
from chronospear.cam.identity import IdentityKind
from chronospear.cam.time import ChronoStamp


@dataclass(frozen=True, slots=True)
class HistoricalOccurrence:
    """Immutable record that something happened in the represented world.

    Historical Occurrences are graph-addressable History, not Identity Nodes and
    not Associations. Slice 2 stores the record but performs no recall,
    interpretation, lifecycle resolution, correction, or Association provenance.
    """

    occurrence_id: OccurrenceId
    stamp: ChronoStamp
    synopsis: str
    story: str
    participants: tuple[NodeId, ...] = ()
    place: NodeId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stamp, ChronoStamp):
            raise TypeError("Historical Occurrence stamp must be a ChronoStamp.")
        if any(not isinstance(participant, NodeId) for participant in self.participants):
            raise TypeError("Historical Occurrence participants must be NodeId values.")
        if self.place is not None and not isinstance(self.place, NodeId):
            raise TypeError("Historical Occurrence place must be a NodeId or None.")
        if not self.participants and self.place is None:
            raise ValueError(
                "Historical Occurrence requires at least one participant or place."
            )
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("Historical Occurrence participants cannot contain duplicates.")

        synopsis = self.synopsis.strip()
        story = self.story.strip()
        if not synopsis:
            raise ValueError("Historical Occurrence synopsis cannot be empty.")
        if not story:
            raise ValueError("Historical Occurrence story cannot be empty.")
        object.__setattr__(self, "synopsis", synopsis)
        object.__setattr__(self, "story", story)


class OccurrenceCatalog:
    """Minimal append-only invariant keeper for Historical Occurrences.

    The catalog validates graph anchors and stable occurrence identity only. It is
    intentionally not a recall index, persistence layer, correction system, or
    semantic event deduplicator.
    """

    def __init__(self, *, nodes: IdentityCatalog) -> None:
        self._nodes = nodes
        self._by_id: dict[OccurrenceId, HistoricalOccurrence] = {}

    def add(self, occurrence: HistoricalOccurrence) -> HistoricalOccurrence:
        for participant in occurrence.participants:
            if not self._nodes.contains(participant):
                raise KeyError(f"Unknown Historical Occurrence participant: {participant}.")

        if occurrence.place is not None:
            if not self._nodes.contains(occurrence.place):
                raise KeyError(f"Unknown Historical Occurrence place: {occurrence.place}.")
            place_node = self._nodes.get(occurrence.place)
            if place_node.kind is not IdentityKind.PLACE:
                raise ValueError(
                    "Historical Occurrence place must reference an IdentityKind.PLACE node."
                )

        existing = self._by_id.get(occurrence.occurrence_id)
        if existing is not None:
            if existing == occurrence:
                return existing
            raise ValueError(
                f"Occurrence ID {occurrence.occurrence_id} is already in use."
            )

        self._by_id[occurrence.occurrence_id] = occurrence
        return occurrence

    def get(self, occurrence_id: OccurrenceId) -> HistoricalOccurrence:
        try:
            return self._by_id[occurrence_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Historical Occurrence: {occurrence_id}.") from exc

    def all(self) -> tuple[HistoricalOccurrence, ...]:
        return tuple(self._by_id.values())
