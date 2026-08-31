from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
import re
from typing import Iterable


class EvidenceState(str, Enum):
    LOCKED = "locked"
    PROVEN = "experimentally_proven"
    HYPOTHESIS = "hypothesis"
    PARKED = "parked"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Concept:
    name: str
    synopsis: str
    description: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DesignAssociation:
    id: str
    source: str
    relationship: str
    target: str
    state: EvidenceState
    provenance: tuple[str, ...] = ()

    def render(self) -> str:
        return f"[{self.id}] [{self.state.value}] {self.source} {self.relationship} {self.target}"


@dataclass(frozen=True)
class DesignOccurrence:
    id: str
    date: str
    participants: tuple[str, ...]
    story: str
    state: EvidenceState

    def render(self) -> str:
        return f"[{self.id}] {self.date} [{self.state.value}] {self.story}"


@dataclass(frozen=True)
class PacketBudget:
    associations_per_concept: int = 2
    history_per_concept: int = 2

    def __post_init__(self) -> None:
        if self.associations_per_concept < 0 or self.history_per_concept < 0:
            raise ValueError("packet budgets must be non-negative")


@dataclass(frozen=True)
class MemoryMapEntry:
    concept: str
    synopsis_supplied: bool
    description_remaining: bool
    associations_remaining: int
    history_remaining: int

    def render(self) -> str:
        return (
            f"- {self.concept}: synopsis={'supplied' if self.synopsis_supplied else 'available'}, "
            f"full_description={'available' if self.description_remaining else 'supplied-or-none'}, "
            f"more_associations={self.associations_remaining}, "
            f"more_history={self.history_remaining}"
        )


@dataclass(frozen=True)
class MemoryPacket:
    question: str
    new_synopses: tuple[Concept, ...]
    full_descriptions: tuple[Concept, ...]
    associations: tuple[DesignAssociation, ...]
    history: tuple[DesignOccurrence, ...]
    memory_map: tuple[MemoryMapEntry, ...]

    def render(self) -> str:
        lines = ["CHRONOSPEAR DESIGN MEMORY PACKET", f"Question: {self.question}"]

        lines.extend(["", "Newly surfaced identity synopses:"])
        if self.new_synopses:
            lines.extend(f"- {c.name}: {c.synopsis}" for c in self.new_synopses)
        else:
            lines.append("- none")

        lines.extend(["", "New full identity descriptions:"])
        if self.full_descriptions:
            lines.extend(f"- {c.name}: {c.description}" for c in self.full_descriptions)
        else:
            lines.append("- none")

        lines.extend(["", "New current associative understanding:"])
        if self.associations:
            lines.extend(f"- {a.render()}" for a in self.associations)
        else:
            lines.append("- none")

        lines.extend(["", "New relevant design history:"])
        if self.history:
            lines.extend(f"- {h.render()}" for h in self.history)
        else:
            lines.append("- none")

        lines.extend(["", "Memory availability map:"])
        lines.extend(entry.render() for entry in self.memory_map)

        lines.extend(
            [
                "",
                "Instructions:",
                "Treat LOCKED as current architecture, EXPERIMENTALLY_PROVEN as test evidence, "
                "HYPOTHESIS as not yet locked, PARKED as deferred, REJECTED as historical only, "
                "and UNRESOLVED as still open. Do not promote a hypothesis into a locked decision. "
                "Use the active reasoning-session protocol to request additional memory.",
            ]
        )
        return "\n".join(lines)

    @property
    def estimated_tokens(self) -> int:
        return ceil(len(self.render()) / 4)


@dataclass
class MemorySession:
    seen_synopses: set[str] = field(default_factory=set)
    seen_descriptions: set[str] = field(default_factory=set)
    seen_associations: set[str] = field(default_factory=set)
    seen_history: set[str] = field(default_factory=set)
    surfaced_concepts: set[str] = field(default_factory=set)


class DesignMemory:
    def __init__(
        self,
        concepts: Iterable[Concept],
        associations: Iterable[DesignAssociation],
        occurrences: Iterable[DesignOccurrence],
    ) -> None:
        self.concepts = {c.name: c for c in concepts}
        self.associations = tuple(associations)
        self.occurrences = tuple(occurrences)
        self._aliases: dict[str, str] = {}
        for concept in self.concepts.values():
            for value in (concept.name, *concept.aliases):
                self._aliases[value.casefold()] = concept.name

    def activate(self, text: str) -> tuple[str, ...]:
        """Deliberately shallow language surface: literal concept/alias mentions only."""
        lowered = text.casefold()
        hits: list[tuple[int, str]] = []
        for alias, canonical in self._aliases.items():
            match = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered)
            if match:
                hits.append((match.start(), canonical))
        ordered: list[str] = []
        for _, canonical in sorted(hits):
            if canonical not in ordered:
                ordered.append(canonical)
        return tuple(ordered)

    def build_initial_packet(
        self,
        question: str,
        session: MemorySession,
        budget: PacketBudget = PacketBudget(),
    ) -> MemoryPacket:
        activated = self.activate(question)
        if not activated:
            raise ValueError("No explicit ChronoSpear concept was activated by the question")
        session.surfaced_concepts.update(activated)
        return self._packet(question, activated, session, budget, include_description=False)

    def expand(
        self,
        concept_name: str,
        session: MemorySession,
        budget: PacketBudget = PacketBudget(),
    ) -> MemoryPacket:
        canonical = self._resolve_name(concept_name)
        if canonical not in session.surfaced_concepts:
            raise ValueError(f"Cannot expand unsurfaced concept: {canonical}")
        return self._packet("EXPANSION", (canonical,), session, budget, include_description=True)

    def expand_channel(
        self,
        concept_name: str,
        channel: str,
        session: MemorySession,
        *,
        page_size: int = 1,
    ) -> MemoryPacket:
        """Reveal one deterministic memory channel without interpreting why it was requested."""
        if page_size < 1:
            raise ValueError("page_size must be at least 1")

        canonical = self._resolve_name(concept_name)
        if canonical not in session.surfaced_concepts:
            raise ValueError(f"Cannot expand unsurfaced concept: {canonical}")

        normalized = channel.casefold().strip()
        if normalized == "description":
            return self._packet(
                "EXPAND DESCRIPTION",
                (canonical,),
                session,
                PacketBudget(0, 0),
                include_description=True,
            )
        if normalized == "associations":
            return self._packet(
                "EXPAND ASSOCIATIONS",
                (canonical,),
                session,
                PacketBudget(page_size, 0),
                include_description=False,
            )
        if normalized == "history":
            return self._packet(
                "EXPAND HISTORY",
                (canonical,),
                session,
                PacketBudget(0, page_size),
                include_description=False,
            )
        raise ValueError("channel must be DESCRIPTION, ASSOCIATIONS, or HISTORY")

    def resolve_surfaced_request(self, request: str, session: MemorySession) -> str | None:
        lowered = request.casefold()
        candidates: list[tuple[int, str]] = []
        for concept_name in session.surfaced_concepts:
            concept = self.concepts[concept_name]
            for alias in (concept.name, *concept.aliases):
                idx = lowered.find(alias.casefold())
                if idx >= 0:
                    candidates.append((idx, concept_name))
        if not candidates:
            return None
        return sorted(candidates)[0][1]

    def _packet(
        self,
        question: str,
        concept_names: tuple[str, ...],
        session: MemorySession,
        budget: PacketBudget,
        *,
        include_description: bool,
    ) -> MemoryPacket:
        selected_assoc: list[DesignAssociation] = []
        selected_hist: list[DesignOccurrence] = []
        selected_descriptions: list[Concept] = []

        if include_description:
            for name in concept_names:
                if name not in session.seen_descriptions and self.concepts[name].description:
                    selected_descriptions.append(self.concepts[name])
                    session.seen_descriptions.add(name)

        for name in concept_names:
            assoc_candidates = [
                a
                for a in self.associations
                if (a.source == name or a.target == name) and a.id not in session.seen_associations
            ]
            for association in assoc_candidates[: budget.associations_per_concept]:
                selected_assoc.append(association)
                session.seen_associations.add(association.id)
                if association.source in self.concepts:
                    session.surfaced_concepts.add(association.source)
                if association.target in self.concepts:
                    session.surfaced_concepts.add(association.target)

            hist_candidates = [
                h
                for h in self.occurrences
                if name in h.participants and h.id not in session.seen_history
            ]
            hist_candidates.sort(key=lambda h: (h.date, h.id), reverse=True)
            for occurrence in hist_candidates[: budget.history_per_concept]:
                selected_hist.append(occurrence)
                session.seen_history.add(occurrence.id)
                for participant in occurrence.participants:
                    if participant in self.concepts:
                        session.surfaced_concepts.add(participant)

        new_synopses: list[Concept] = []
        for name in sorted(session.surfaced_concepts):
            if name not in session.seen_synopses:
                new_synopses.append(self.concepts[name])
                session.seen_synopses.add(name)

        memory_map = tuple(self._map_entry(name, session) for name in sorted(session.surfaced_concepts))
        return MemoryPacket(
            question=question,
            new_synopses=tuple(new_synopses),
            full_descriptions=tuple(selected_descriptions),
            associations=tuple(selected_assoc),
            history=tuple(selected_hist),
            memory_map=memory_map,
        )

    def _map_entry(self, name: str, session: MemorySession) -> MemoryMapEntry:
        remaining_assoc = sum(
            1
            for a in self.associations
            if (a.source == name or a.target == name) and a.id not in session.seen_associations
        )
        remaining_hist = sum(
            1
            for h in self.occurrences
            if name in h.participants and h.id not in session.seen_history
        )
        concept = self.concepts[name]
        return MemoryMapEntry(
            concept=name,
            synopsis_supplied=name in session.seen_synopses,
            description_remaining=bool(concept.description) and name not in session.seen_descriptions,
            associations_remaining=remaining_assoc,
            history_remaining=remaining_hist,
        )

    def _resolve_name(self, value: str) -> str:
        key = value.casefold().strip()
        if key in self._aliases:
            return self._aliases[key]
        if value in self.concepts:
            return value
        raise KeyError(value)
