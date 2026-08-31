from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil
from typing import Protocol, Sequence


@dataclass(frozen=True)
class PacketBudget:
    recent_chat: int = 2
    recent_history: int = 3
    effective_associations: int = 3

    def __post_init__(self) -> None:
        for name, value in (
            ("recent_chat", self.recent_chat),
            ("recent_history", self.recent_history),
            ("effective_associations", self.effective_associations),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class ActivatedObject:
    name: str
    description: str = ""


@dataclass(frozen=True)
class PacketSource:
    perspective: str
    latest_interaction: str
    activated_objects: tuple[ActivatedObject, ...]
    recent_chat: tuple[str, ...]
    recent_history: tuple[str, ...]
    effective_associations: tuple[str, ...]


@dataclass(frozen=True)
class PacketTaxation:
    chat_items: int
    history_items: int
    association_items: int
    activated_objects: int
    characters: int
    estimated_tokens: int


@dataclass(frozen=True)
class InitialPacket:
    perspective: str
    latest_interaction: str
    activated_objects: tuple[ActivatedObject, ...]
    recent_chat: tuple[str, ...]
    recent_history: tuple[str, ...]
    effective_associations: tuple[str, ...]
    instructions: str
    taxation: PacketTaxation

    def render(self) -> str:
        lines = [
            "CHRONOSPEAR INITIAL MEMORY PACKET",
            f"Perspective: {self.perspective}",
            f"Latest interaction: {self.latest_interaction}",
            "",
            "Activated objects:",
        ]
        if self.activated_objects:
            for obj in self.activated_objects:
                if obj.description:
                    lines.append(f"- {obj.name}: {obj.description}")
                else:
                    lines.append(f"- {obj.name}")
        else:
            lines.append("- none")

        lines.extend(["", "Recent chat:"])
        lines.extend(f"- {item}" for item in self.recent_chat)
        if not self.recent_chat:
            lines.append("- none")

        lines.extend(["", "Recent history:"])
        lines.extend(f"- {item}" for item in self.recent_history)
        if not self.recent_history:
            lines.append("- none")

        lines.extend(["", "Effective associations:"])
        lines.extend(f"- {item}" for item in self.effective_associations)
        if not self.effective_associations:
            lines.append("- none")

        lines.extend(["", "Instructions:", self.instructions])
        return "\n".join(lines)

    def memory_fingerprint(self) -> tuple[object, ...]:
        """Return the memory content independent of the latest interaction wording."""
        return (
            self.perspective,
            self.activated_objects,
            self.recent_chat,
            self.recent_history,
            self.effective_associations,
            self.instructions,
        )


DEFAULT_INSTRUCTIONS = (
    "Reason only from the supplied memory. If it is insufficient, request the additional "
    "memory you need in ordinary language. Do not invent missing facts."
)


class InitialPacketBuilder:
    """A deliberately dumb, fixed-budget packet builder.

    The builder does not inspect the interaction text to decide which history or associations
    matter. It receives already-activated CAM objects and slices preselected local memory by
    fixed budgets only.
    """

    def __init__(self, budget: PacketBudget = PacketBudget()) -> None:
        self._budget = budget

    def build(self, source: PacketSource) -> InitialPacket:
        packet_without_tax = InitialPacket(
            perspective=source.perspective,
            latest_interaction=source.latest_interaction,
            activated_objects=source.activated_objects,
            recent_chat=self._tail(source.recent_chat, self._budget.recent_chat),
            recent_history=self._tail(source.recent_history, self._budget.recent_history),
            effective_associations=self._tail(
                source.effective_associations,
                self._budget.effective_associations,
            ),
            instructions=DEFAULT_INSTRUCTIONS,
            taxation=PacketTaxation(0, 0, 0, 0, 0, 0),
        )
        rendered = packet_without_tax.render()
        taxation = PacketTaxation(
            chat_items=len(packet_without_tax.recent_chat),
            history_items=len(packet_without_tax.recent_history),
            association_items=len(packet_without_tax.effective_associations),
            activated_objects=len(packet_without_tax.activated_objects),
            characters=len(rendered),
            estimated_tokens=ceil(len(rendered) / 4),
        )
        return InitialPacket(
            perspective=packet_without_tax.perspective,
            latest_interaction=packet_without_tax.latest_interaction,
            activated_objects=packet_without_tax.activated_objects,
            recent_chat=packet_without_tax.recent_chat,
            recent_history=packet_without_tax.recent_history,
            effective_associations=packet_without_tax.effective_associations,
            instructions=packet_without_tax.instructions,
            taxation=taxation,
        )

    @staticmethod
    def _tail(items: Sequence[str], count: int) -> tuple[str, ...]:
        if count == 0:
            return ()
        return tuple(items[-count:])


class DecisionKind(str, Enum):
    ANSWER = "answer"
    REQUEST_MORE = "request_more"


@dataclass(frozen=True)
class LlmDecision:
    kind: DecisionKind
    text: str


class LlmProvider(Protocol):
    def respond(self, packet_text: str) -> LlmDecision: ...


class ExpansionProvider(Protocol):
    def expand(self, request: str) -> str: ...


@dataclass(frozen=True)
class ReasoningRun:
    initial_packet: InitialPacket
    first_decision: LlmDecision
    expansion_request: str | None
    expansion_text: str | None
    final_decision: LlmDecision
    provider_calls: int


class ReasoningHarness:
    """Minimal two-step harness used to observe whether an LLM can ask useful questions."""

    def __init__(self, provider: LlmProvider, expansion_provider: ExpansionProvider) -> None:
        self._provider = provider
        self._expansion_provider = expansion_provider

    def run(self, packet: InitialPacket) -> ReasoningRun:
        first = self._provider.respond(packet.render())
        if first.kind is DecisionKind.ANSWER:
            return ReasoningRun(packet, first, None, None, first, 1)

        request = first.text.strip()
        if not request:
            raise ValueError("request_more decisions must include a natural-language request")

        expansion = self._expansion_provider.expand(request)
        follow_up_packet = (
            f"{packet.render()}\n\nADDITIONAL MEMORY REQUESTED BY MODEL:\n{request}\n\n"
            f"ADDITIONAL MEMORY:\n{expansion}"
        )
        final = self._provider.respond(follow_up_packet)
        return ReasoningRun(packet, first, request, expansion, final, 2)


class ScriptedProvider:
    """Deterministic provider for testing the harness without pretending it is an LLM."""

    def __init__(self, decisions: Sequence[LlmDecision]) -> None:
        self._decisions = list(decisions)
        self.seen_packets: list[str] = []

    def respond(self, packet_text: str) -> LlmDecision:
        self.seen_packets.append(packet_text)
        if not self._decisions:
            raise RuntimeError("No scripted decision remains")
        return self._decisions.pop(0)


class ScriptedExpansionProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests: list[str] = []

    def expand(self, request: str) -> str:
        self.requests.append(request)
        return self.response
