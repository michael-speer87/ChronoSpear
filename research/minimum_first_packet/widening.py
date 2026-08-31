from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Sequence

from experiment import InitialPacket, PacketSource


@dataclass(frozen=True)
class ExpansionBudget:
    recent_history: int = 0
    effective_associations: int = 1

    def __post_init__(self) -> None:
        if self.recent_history < 0:
            raise ValueError("recent_history must be non-negative")
        if self.effective_associations < 0:
            raise ValueError("effective_associations must be non-negative")


@dataclass(frozen=True)
class ExpansionTaxation:
    history_items: int
    association_items: int
    characters: int
    estimated_tokens: int


@dataclass(frozen=True)
class FixedMemoryExpansion:
    request: str
    recent_history: tuple[str, ...]
    effective_associations: tuple[str, ...]
    taxation: ExpansionTaxation

    def render(self) -> str:
        lines = ["CHRONOSPEAR FIXED WIDENING EXPANSION", "", "Additional history:"]
        lines.extend(f"- {item}" for item in self.recent_history)
        if not self.recent_history:
            lines.append("- none")

        lines.extend(["", "Additional associations:"])
        lines.extend(f"- {item}" for item in self.effective_associations)
        if not self.effective_associations:
            lines.append("- none")

        lines.extend(
            [
                "",
                "Selection note:",
                "This is the next fixed-budget page from the already activated local memory. "
                "The request wording was not used to select these items.",
            ]
        )
        return "\n".join(lines)

    def memory_fingerprint(self) -> tuple[object, ...]:
        """Return selected memory independent of the model's request wording."""
        return (self.recent_history, self.effective_associations)


class FixedWideningProvider:
    """Expose the next omitted page without interpreting the model's request.

    This experiment treats REQUEST_MORE as only a widening signal. The natural-language request
    is retained for observation, but it does not influence which memory items are selected.
    """

    def __init__(
        self,
        source: PacketSource,
        initial_packet: InitialPacket,
        budget: ExpansionBudget = ExpansionBudget(),
    ) -> None:
        self._source = source
        self._initial_packet = initial_packet
        self._budget = budget

    def expand(self, request: str) -> FixedMemoryExpansion:
        if not request.strip():
            raise ValueError("expansion request must not be blank")

        history = self._previous_page(
            self._source.recent_history,
            self._initial_packet.recent_history,
            self._budget.recent_history,
        )
        associations = self._previous_page(
            self._source.effective_associations,
            self._initial_packet.effective_associations,
            self._budget.effective_associations,
        )

        untaxed = FixedMemoryExpansion(
            request=request.strip(),
            recent_history=history,
            effective_associations=associations,
            taxation=ExpansionTaxation(0, 0, 0, 0),
        )
        rendered = untaxed.render()
        return FixedMemoryExpansion(
            request=untaxed.request,
            recent_history=untaxed.recent_history,
            effective_associations=untaxed.effective_associations,
            taxation=ExpansionTaxation(
                history_items=len(history),
                association_items=len(associations),
                characters=len(rendered),
                estimated_tokens=ceil(len(rendered) / 4),
            ),
        )

    @staticmethod
    def _previous_page(
        full: Sequence[str],
        already_selected: Sequence[str],
        count: int,
    ) -> tuple[str, ...]:
        full_tuple = tuple(full)
        selected_tuple = tuple(already_selected)

        if selected_tuple:
            if len(selected_tuple) > len(full_tuple):
                raise ValueError("initial packet contains more items than its source")
            if full_tuple[-len(selected_tuple) :] != selected_tuple:
                raise ValueError("initial packet is not the expected tail of its source")
            omitted = full_tuple[: -len(selected_tuple)]
        else:
            omitted = full_tuple

        if count == 0:
            return ()
        return omitted[-count:]
