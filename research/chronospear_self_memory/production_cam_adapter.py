"""Read-only production CAM adapter for the CAM-native research protocol."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import ceil

from chronospear.cam import Association, HistoricalOccurrence, IdentityNode
from chronospear.world_import import ImportedWorld


@dataclass(frozen=True)
class ProductionConcept:
    name: str
    synopsis: str
    description: str


@dataclass(frozen=True)
class ProductionAssociation:
    identifier: str
    source: str
    relationship: str
    target: str

    def render(self) -> str:
        return f"[{self.identifier}] {self.source} {self.relationship} {self.target}"


@dataclass(frozen=True)
class ProductionOccurrence:
    identifier: str
    world_time: int
    system_time: int
    participants: tuple[str, ...]
    place: str
    synopsis: str
    story: str
    started_associations: tuple[str, ...]
    ended_associations: tuple[str, ...]

    def render(self) -> str:
        participants = ", ".join(self.participants)
        started = ", ".join(self.started_associations) or "none"
        ended = ", ".join(self.ended_associations) or "none"
        return (
            f"[{self.identifier}] WT={self.world_time} ST={self.system_time} | "
            f"participants={participants} | place={self.place} | {self.synopsis} | "
            f"{self.story} | STARTED={started} | ENDED={ended}"
        )


@dataclass(frozen=True)
class ProductionMemoryMapEntry:
    concept: str
    synopsis_supplied: bool
    description_remaining: bool
    associations_remaining: int
    history_remaining: int

    def render(self) -> str:
        return (
            f"- {self.concept}: synopsis="
            f"{'supplied' if self.synopsis_supplied else 'available'}, "
            "full_description="
            f"{'available' if self.description_remaining else 'supplied-or-none'}, "
            f"more_associations={self.associations_remaining}, "
            f"more_history={self.history_remaining}"
        )


@dataclass(frozen=True)
class ProductionMemoryPacket:
    question: str
    new_synopses: tuple[ProductionConcept, ...]
    full_descriptions: tuple[ProductionConcept, ...]
    associations: tuple[ProductionAssociation, ...]
    history: tuple[ProductionOccurrence, ...]
    memory_map: tuple[ProductionMemoryMapEntry, ...]

    def render(self) -> str:
        lines = ["CHRONOSPEAR PRODUCTION CAM PACKET", f"Question: {self.question}"]
        lines.extend(["", "Newly surfaced identity orientation:"])
        if self.new_synopses:
            lines.extend(
                f"- {concept.name}: {concept.synopsis or '(no synopsis)'}"
                for concept in self.new_synopses
            )
        else:
            lines.append("- none")
        lines.extend(["", "New full identity descriptions:"])
        if self.full_descriptions:
            lines.extend(
                f"- {concept.name}: {concept.description}"
                for concept in self.full_descriptions
            )
        else:
            lines.append("- none")
        lines.extend(["", "New production Associations:"])
        lines.extend(
            (f"- {association.render()}" for association in self.associations),
        )
        if not self.associations:
            lines.append("- none")
        lines.extend(["", "New production Historical Occurrences:"])
        lines.extend(f"- {occurrence.render()}" for occurrence in self.history)
        if not self.history:
            lines.append("- none")
        lines.extend(["", "Memory availability map:"])
        lines.extend(entry.render() for entry in self.memory_map)
        lines.extend(
            [
                "",
                "Instructions:",
                "Use the active CAM-native protocol to request additional memory or answer. "
                "CAM supplies records mechanically; you decide what they mean for the question.",
            ]
        )
        return "\n".join(lines)

    @property
    def estimated_tokens(self) -> int:
        return ceil(len(self.render()) / 4)


@dataclass
class ProductionMemorySession:
    seen_synopses: set[str] = field(default_factory=set)
    seen_descriptions: set[str] = field(default_factory=set)
    seen_associations: set[str] = field(default_factory=set)
    seen_history: set[str] = field(default_factory=set)
    surfaced_concepts: set[str] = field(default_factory=set)


class ProductionCamAdapter:
    """Mechanically expose production CAM; never choose semantically useful evidence."""

    def __init__(self, world: ImportedWorld) -> None:
        self.world = world
        self._by_name: dict[str, IdentityNode] = {}
        for identity in world.identities.all():
            if not identity.name:
                continue
            folded = identity.name.casefold()
            if folded in self._by_name:
                raise ValueError(
                    f"Production question harness requires unique nonblank Identity names; "
                    f"duplicate: {identity.name!r}."
                )
            self._by_name[folded] = identity

    def activate_question(self, question: str) -> tuple[str, ...]:
        """Temporary language seam: whole-name literal matching only."""

        hits: list[tuple[int, str]] = []
        lowered = question.casefold()
        for folded, identity in self._by_name.items():
            match = re.search(rf"(?<!\w){re.escape(folded)}(?!\w)", lowered)
            if match:
                hits.append((match.start(), identity.name))
        return tuple(name for _, name in sorted(hits))

    def build_initial_packet(
        self, question: str, session: ProductionMemorySession
    ) -> ProductionMemoryPacket:
        activated = self.activate_question(question)
        if not activated:
            raise ValueError("No literal production Identity name was activated by the question")
        session.surfaced_concepts.update(activated)
        return self._packet(
            question,
            activated,
            session,
            association_limit=3,
            history_limit=5,
            include_description=True,
        )

    def activate(
        self, concept: str, session: ProductionMemorySession
    ) -> ProductionMemoryPacket:
        canonical = self.resolve_name(concept)
        if canonical in session.surfaced_concepts:
            return self.feedback(
                session, f"ACTIVATE {canonical} is already surfaced"
            )
        session.surfaced_concepts.add(canonical)
        return self._packet(
            "ACTIVATION",
            (canonical,),
            session,
            association_limit=0,
            history_limit=0,
            include_description=False,
        )

    def expand(
        self, concept: str, channel: str, session: ProductionMemorySession
    ) -> ProductionMemoryPacket:
        canonical = self.resolve_name(concept)
        if canonical not in session.surfaced_concepts:
            return self.feedback(session, f"{canonical} is not currently surfaced")
        state = self.expansion_state(canonical, channel, session)
        if state != "available":
            return self.feedback(
                session,
                f"EXPAND {canonical} {channel.upper()} is {state.replace('_', ' ')}",
            )
        normalized = channel.upper()
        return self._packet(
            f"EXPAND {normalized}",
            (canonical,),
            session,
            association_limit=1 if normalized == "ASSOCIATIONS" else 0,
            history_limit=1 if normalized == "HISTORY" else 0,
            include_description=normalized == "DESCRIPTION",
        )

    def expansion_state(
        self, concept: str, channel: str, session: ProductionMemorySession
    ) -> str:
        identity = self.identity(concept)
        normalized = channel.upper()
        if normalized == "DESCRIPTION":
            if concept in session.seen_descriptions:
                return "already_supplied"
            return "available" if identity.description else "unavailable"
        if normalized == "ASSOCIATIONS":
            ids = {str(item.association_id) for item in self._associations(identity)}
            if not ids:
                return "unavailable"
            return "already_supplied" if ids <= session.seen_associations else "available"
        if normalized == "HISTORY":
            ids = {str(item.occurrence_id) for item in self._history(identity)}
            if not ids:
                return "unavailable"
            return "already_supplied" if ids <= session.seen_history else "available"
        return "unavailable"

    def feedback(
        self, session: ProductionMemorySession, reason: str
    ) -> ProductionMemoryPacket:
        return ProductionMemoryPacket(
            question=f"CAM REQUEST REJECTED: {reason}. No new memory was supplied.",
            new_synopses=(),
            full_descriptions=(),
            associations=(),
            history=(),
            memory_map=self._memory_map(session),
        )

    def resolve_name(self, name: str) -> str:
        identity = self._by_name.get(name.casefold().strip())
        if identity is None:
            raise KeyError(f"Unknown production Identity name: {name!r}")
        return identity.name

    def identity(self, name: str) -> IdentityNode:
        return self._by_name[name.casefold()]

    def _packet(
        self,
        question: str,
        concepts: tuple[str, ...],
        session: ProductionMemorySession,
        *,
        association_limit: int,
        history_limit: int,
        include_description: bool,
    ) -> ProductionMemoryPacket:
        descriptions: list[ProductionConcept] = []
        for name in concepts:
            identity = self.identity(name)
            if (
                include_description
                and identity.description
                and name not in session.seen_descriptions
            ):
                descriptions.append(self._concept(identity))
                session.seen_descriptions.add(name)

        selected_identities = {self.identity(name).identity_id for name in concepts}
        association_candidates = [
            item
            for item in self.world.associations.all()
            if (
                item.source in selected_identities or item.target in selected_identities
            )
            and str(item.association_id) not in session.seen_associations
        ]
        association_candidates.sort(key=lambda item: str(item.association_id))
        selected_associations = association_candidates[:association_limit]
        associations = [self._association(item) for item in selected_associations]
        for association in selected_associations:
            session.seen_associations.add(str(association.association_id))
            self._surface_association_neighbors(association, session)

        history_candidates = [
            item
            for item in self.world.occurrences.all()
            if (
                selected_identities.intersection(item.participants)
                or item.place in selected_identities
            )
            and str(item.occurrence_id) not in session.seen_history
        ]
        history_candidates.sort(
            key=lambda item: (
                item.stamp.world_time.value,
                item.stamp.system_time.value,
                str(item.occurrence_id),
            ),
            reverse=True,
        )
        selected_history = history_candidates[:history_limit]
        history = [self._occurrence(item) for item in selected_history]
        for occurrence in selected_history:
            session.seen_history.add(str(occurrence.occurrence_id))
            self._surface_occurrence_neighbors(occurrence, session)
        orientations = [
            self._concept(self.identity(name))
            for name in sorted(session.surfaced_concepts)
            if name not in session.seen_synopses
        ]
        session.seen_synopses.update(item.name for item in orientations)
        return ProductionMemoryPacket(
            question=question,
            new_synopses=tuple(orientations),
            full_descriptions=tuple(descriptions),
            associations=tuple(associations),
            history=tuple(history),
            memory_map=self._memory_map(session),
        )

    def _associations(self, identity: IdentityNode) -> tuple[Association, ...]:
        return tuple(
            item
            for item in self.world.associations.all()
            if item.source == identity.identity_id or item.target == identity.identity_id
        )

    def _history(self, identity: IdentityNode) -> tuple[HistoricalOccurrence, ...]:
        return tuple(
            item
            for item in self.world.occurrences.all()
            if identity.identity_id in item.participants or item.place == identity.identity_id
        )

    def _surface_association_neighbors(
        self, association: Association, session: ProductionMemorySession
    ) -> None:
        for identity_id in (association.source, association.target):
            identity = self.world.identities.get(identity_id)
            if identity.name:
                session.surfaced_concepts.add(identity.name)

    def _surface_occurrence_neighbors(
        self, occurrence: HistoricalOccurrence, session: ProductionMemorySession
    ) -> None:
        for identity_id in (*occurrence.participants, occurrence.place):
            identity = self.world.identities.get(identity_id)
            if identity.name:
                session.surfaced_concepts.add(identity.name)

    @staticmethod
    def _concept(identity: IdentityNode) -> ProductionConcept:
        return ProductionConcept(identity.name, identity.synopsis, identity.description)

    def _association(self, association: Association) -> ProductionAssociation:
        return ProductionAssociation(
            str(association.association_id),
            self.world.identities.get(association.source).name,
            association.relationship.name,
            self.world.identities.get(association.target).name,
        )

    def _occurrence(self, occurrence: HistoricalOccurrence) -> ProductionOccurrence:
        return ProductionOccurrence(
            identifier=str(occurrence.occurrence_id),
            world_time=occurrence.stamp.world_time.value,
            system_time=occurrence.stamp.system_time.value,
            participants=tuple(
                self.world.identities.get(item).name for item in occurrence.participants
            ),
            place=self.world.identities.get(occurrence.place).name,
            synopsis=occurrence.synopsis,
            story=occurrence.story,
            started_associations=tuple(map(str, occurrence.started_associations)),
            ended_associations=tuple(map(str, occurrence.ended_associations)),
        )

    def _memory_map(
        self, session: ProductionMemorySession
    ) -> tuple[ProductionMemoryMapEntry, ...]:
        entries: list[ProductionMemoryMapEntry] = []
        for name in sorted(session.surfaced_concepts):
            identity = self.identity(name)
            entries.append(
                ProductionMemoryMapEntry(
                    concept=name,
                    synopsis_supplied=name in session.seen_synopses,
                    description_remaining=bool(identity.description)
                    and name not in session.seen_descriptions,
                    associations_remaining=sum(
                        str(item.association_id) not in session.seen_associations
                        for item in self._associations(identity)
                    ),
                    history_remaining=sum(
                        str(item.occurrence_id) not in session.seen_history
                        for item in self._history(identity)
                    ),
                )
            )
        return tuple(entries)
