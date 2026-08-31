from __future__ import annotations

import unittest

from memory import EvidenceState, MemorySession, PacketBudget
from seed import build_memory


class ChronoSpearSelfMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = build_memory()

    def test_language_activation_is_literal_not_query_semantic(self) -> None:
        self.assertEqual(self.memory.activate("What is a Description allowed to contain?"), ("Description",))
        self.assertEqual(self.memory.activate("Where should Alric be?"), ())

    def test_initial_packet_supplies_synopsis_not_full_description(self) -> None:
        session = MemorySession()
        packet = self.memory.build_initial_packet("What is a Description allowed to contain?", session)
        self.assertIn("Description", session.seen_synopses)
        self.assertNotIn("Description", session.seen_descriptions)
        self.assertTrue(any(c.name == "Description" for c in packet.new_synopses))
        self.assertEqual(packet.full_descriptions, ())

    def test_expansion_is_delta_and_adds_full_description_once(self) -> None:
        session = MemorySession()
        first = self.memory.build_initial_packet(
            "What evidence do we have that Packet #1 can stay question-agnostic?",
            session,
            PacketBudget(associations_per_concept=1, history_per_concept=1),
        )
        second = self.memory.expand(
            "Packet #1", session, PacketBudget(associations_per_concept=1, history_per_concept=1)
        )
        third = self.memory.expand(
            "Packet #1", session, PacketBudget(associations_per_concept=1, history_per_concept=1)
        )
        first_ids = {a.id for a in first.associations} | {h.id for h in first.history}
        second_ids = {a.id for a in second.associations} | {h.id for h in second.history}
        third_ids = {a.id for a in third.associations} | {h.id for h in third.history}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertTrue(first_ids.isdisjoint(third_ids))
        self.assertTrue(second_ids.isdisjoint(third_ids))
        self.assertEqual([c.name for c in second.full_descriptions], ["Packet #1"])
        self.assertEqual(third.full_descriptions, ())

    def test_current_and_historical_confidence_are_explicit(self) -> None:
        states = {occurrence.id: occurrence.state for occurrence in self.memory.occurrences}
        self.assertEqual(states["o-0826-desc"], EvidenceState.LOCKED)
        self.assertEqual(states["o-0831-live"], EvidenceState.PROVEN)
        self.assertEqual(states["o-0831-map"], EvidenceState.HYPOTHESIS)
        self.assertEqual(states["o-0830-mcp"], EvidenceState.UNRESOLVED)

    def test_unsurfaced_concept_cannot_be_expanded(self) -> None:
        session = MemorySession()
        self.memory.build_initial_packet("What does COLD mean?", session)
        with self.assertRaises(ValueError):
            self.memory.expand("MCP", session)

    def test_memory_map_reports_remaining_depth(self) -> None:
        session = MemorySession()
        packet = self.memory.build_initial_packet(
            "What does COLD mean?", session, PacketBudget(associations_per_concept=0, history_per_concept=0)
        )
        entry = next(e for e in packet.memory_map if e.concept == "HOT/WARM/COLD")
        self.assertTrue(entry.description_remaining)
        self.assertGreater(entry.associations_remaining, 0)
        self.assertGreater(entry.history_remaining, 0)


if __name__ == "__main__":
    unittest.main()
