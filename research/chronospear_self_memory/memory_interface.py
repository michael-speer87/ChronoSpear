from __future__ import annotations

from dataclasses import dataclass

from memory import Concept, DesignAssociation, DesignMemory, DesignOccurrence, EvidenceState


@dataclass(frozen=True)
class IntegrityReport:
    dangling_association_sources: tuple[str, ...]
    dangling_association_targets: tuple[str, ...]
    dangling_occurrence_participants: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (
            self.dangling_association_sources
            or self.dangling_association_targets
            or self.dangling_occurrence_participants
        )


class MemoryInterface:
    """Research-only mutation surface for the self-memory playground.

    Mutations affect only the in-memory DesignMemory instance. Nothing is written
    back to seed.py. Concept deletion is deliberately non-cascading so integrity
    failures stay visible instead of being silently repaired.
    """

    def __init__(self, memory: DesignMemory) -> None:
        self.memory = memory

    def add_concept(
        self,
        name: str,
        synopsis: str,
        description: str,
        aliases: tuple[str, ...] = (),
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("concept name cannot be empty")
        if name in self.memory.concepts:
            raise ValueError(f"concept already exists: {name}")
        self.memory.concepts[name] = Concept(name, synopsis.strip(), description.strip(), aliases)
        self._rebuild_aliases()

    def remove_concept(self, name: str) -> Concept:
        canonical = self._resolve_concept(name)
        removed = self.memory.concepts.pop(canonical)
        self._rebuild_aliases()
        return removed

    def add_association(
        self,
        evidence_id: str,
        source: str,
        relationship: str,
        target: str,
        state: EvidenceState,
        provenance: tuple[str, ...] = (),
    ) -> None:
        evidence_id = evidence_id.strip()
        if not evidence_id:
            raise ValueError("association evidence ID cannot be empty")
        if any(item.id == evidence_id for item in self.memory.associations):
            raise ValueError(f"association ID already exists: {evidence_id}")
        item = DesignAssociation(
            evidence_id,
            source.strip(),
            relationship.strip(),
            target.strip(),
            state,
            provenance,
        )
        self.memory.associations = (*self.memory.associations, item)

    def remove_association(self, evidence_id: str) -> DesignAssociation:
        for item in self.memory.associations:
            if item.id == evidence_id:
                self.memory.associations = tuple(candidate for candidate in self.memory.associations if candidate.id != evidence_id)
                return item
        raise KeyError(evidence_id)

    def add_occurrence(
        self,
        evidence_id: str,
        date: str,
        participants: tuple[str, ...],
        story: str,
        state: EvidenceState,
    ) -> None:
        evidence_id = evidence_id.strip()
        if not evidence_id:
            raise ValueError("occurrence evidence ID cannot be empty")
        if any(item.id == evidence_id for item in self.memory.occurrences):
            raise ValueError(f"occurrence ID already exists: {evidence_id}")
        item = DesignOccurrence(
            evidence_id,
            date.strip(),
            tuple(value.strip() for value in participants if value.strip()),
            story.strip(),
            state,
        )
        self.memory.occurrences = (*self.memory.occurrences, item)

    def remove_occurrence(self, evidence_id: str) -> DesignOccurrence:
        for item in self.memory.occurrences:
            if item.id == evidence_id:
                self.memory.occurrences = tuple(candidate for candidate in self.memory.occurrences if candidate.id != evidence_id)
                return item
        raise KeyError(evidence_id)

    def integrity_report(self) -> IntegrityReport:
        concept_names = set(self.memory.concepts)
        dangling_sources = sorted(
            {item.source for item in self.memory.associations if item.source not in concept_names}
        )
        # Association targets may intentionally be literal values rather than Concepts.
        # Only flag targets that look like references to a formerly known Concept by
        # checking whether they appear as participants/sources elsewhere.
        known_reference_names = {
            item.source for item in self.memory.associations
        } | {
            participant
            for occurrence in self.memory.occurrences
            for participant in occurrence.participants
        }
        dangling_targets = sorted(
            {
                item.target
                for item in self.memory.associations
                if item.target in known_reference_names and item.target not in concept_names
            }
        )
        dangling_participants = sorted(
            {
                participant
                for occurrence in self.memory.occurrences
                for participant in occurrence.participants
                if participant not in concept_names
            }
        )
        return IntegrityReport(
            tuple(dangling_sources),
            tuple(dangling_targets),
            tuple(dangling_participants),
        )

    def _resolve_concept(self, value: str) -> str:
        key = value.casefold().strip()
        if key in self.memory._aliases:
            return self.memory._aliases[key]
        if value in self.memory.concepts:
            return value
        raise KeyError(value)

    def _rebuild_aliases(self) -> None:
        aliases: dict[str, str] = {}
        for concept in self.memory.concepts.values():
            for value in (concept.name, *concept.aliases):
                aliases[value.casefold()] = concept.name
        self.memory._aliases = aliases
