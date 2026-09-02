from __future__ import annotations

from dataclasses import dataclass

from chronospear.cam.associations import AssociationCatalog
from chronospear.cam.catalog import IdentityCatalog
from chronospear.cam.identifiers import AssociationId, IdentityId, OccurrenceId
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
    participants: tuple[IdentityId, ...]
    place: IdentityId
    started_associations: tuple[AssociationId, ...] = ()
    ended_associations: tuple[AssociationId, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stamp, ChronoStamp):
            raise TypeError("Historical Occurrence stamp must be a ChronoStamp.")
        if any(not isinstance(participant, IdentityId) for participant in self.participants):
            raise TypeError("Historical Occurrence participants must be IdentityId values.")
        if not isinstance(self.place, IdentityId):
            raise TypeError("Historical Occurrence place must be an IdentityId.")
        if not isinstance(self.started_associations, tuple):
            raise TypeError(
                "Historical Occurrence started Associations must be a tuple."
            )
        if not isinstance(self.ended_associations, tuple):
            raise TypeError("Historical Occurrence ended Associations must be a tuple.")
        if any(
            not isinstance(association_id, AssociationId)
            for association_id in self.started_associations
        ):
            raise TypeError(
                "Historical Occurrence started Associations must be AssociationId values."
            )
        if any(
            not isinstance(association_id, AssociationId)
            for association_id in self.ended_associations
        ):
            raise TypeError(
                "Historical Occurrence ended Associations must be AssociationId values."
            )
        if not self.participants:
            raise ValueError(
                "Historical Occurrence requires at least one Entity participant."
            )
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("Historical Occurrence participants cannot contain duplicates.")
        if len(set(self.started_associations)) != len(self.started_associations):
            raise ValueError(
                "Historical Occurrence started Associations cannot contain duplicates."
            )
        if len(set(self.ended_associations)) != len(self.ended_associations):
            raise ValueError(
                "Historical Occurrence ended Associations cannot contain duplicates."
            )
        if set(self.started_associations) & set(self.ended_associations):
            raise ValueError(
                "A Historical Occurrence cannot both start and end the same Association."
            )

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

    The catalog validates Identity and Association anchors plus stable occurrence
    identity. It is intentionally not a recall index, lifecycle resolver,
    persistence layer, correction system, or semantic event deduplicator.
    """

    def __init__(
        self,
        *,
        nodes: IdentityCatalog,
        associations: AssociationCatalog,
    ) -> None:
        self._nodes = nodes
        self._associations = associations
        self._by_id: dict[OccurrenceId, HistoricalOccurrence] = {}

    def create(
        self,
        *,
        stamp: ChronoStamp,
        synopsis: str,
        story: str,
        participants: tuple[IdentityId, ...],
        place: IdentityId,
        started_associations: tuple[AssociationId, ...] = (),
        ended_associations: tuple[AssociationId, ...] = (),
    ) -> HistoricalOccurrence:
        """Create and store an occurrence with a CAM-owned typed UUID4."""

        return self.add(
            HistoricalOccurrence(
                occurrence_id=OccurrenceId.new(),
                stamp=stamp,
                synopsis=synopsis,
                story=story,
                participants=participants,
                place=place,
                started_associations=started_associations,
                ended_associations=ended_associations,
            )
        )

    def add(self, occurrence: HistoricalOccurrence) -> HistoricalOccurrence:
        for participant in occurrence.participants:
            if not self._nodes.contains(participant):
                raise KeyError(f"Unknown Historical Occurrence participant: {participant}.")
            participant_node = self._nodes.get(participant)
            if participant_node.kind is not IdentityKind.ENTITY:
                raise ValueError(
                    "Historical Occurrence participants must reference "
                    "IdentityKind.ENTITY identities."
                )

        if not self._nodes.contains(occurrence.place):
            raise KeyError(f"Unknown Historical Occurrence place: {occurrence.place}.")
        place_node = self._nodes.get(occurrence.place)
        if place_node.kind is not IdentityKind.PLACE:
            raise ValueError(
                "Historical Occurrence place must reference an IdentityKind.PLACE identity."
            )

        for association_id in occurrence.started_associations:
            try:
                self._associations.get(association_id)
            except KeyError as exc:
                raise KeyError(
                    "Unknown Historical Occurrence started Association: "
                    f"{association_id}."
                ) from exc
        for association_id in occurrence.ended_associations:
            try:
                self._associations.get(association_id)
            except KeyError as exc:
                raise KeyError(
                    "Unknown Historical Occurrence ended Association: "
                    f"{association_id}."
                ) from exc

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
