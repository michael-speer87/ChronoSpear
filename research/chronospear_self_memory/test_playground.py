from __future__ import annotations

import unittest

from memory import MemorySession
from playground import EXPANSION_BUDGET, INITIAL_BUDGET
from seed import build_memory


class PlaygroundContractTests(unittest.TestCase):
    def test_initial_packet_is_synopsis_only(self) -> None:
        memory = build_memory()
        session = MemorySession()

        packet = memory.build_initial_packet(
            "What semantic risk did Expansion expose?",
            session,
            INITIAL_BUDGET,
        )

        self.assertGreaterEqual(len(packet.new_synopses), 1)
        self.assertEqual(packet.full_descriptions, ())
        self.assertEqual(packet.associations, ())
        self.assertEqual(packet.history, ())
        self.assertTrue(any(entry.concept == "Expansion" for entry in packet.memory_map))

    def test_expansion_is_bounded_and_deduplicated(self) -> None:
        memory = build_memory()
        session = MemorySession()
        memory.build_initial_packet(
            "What semantic risk did Expansion expose?",
            session,
            INITIAL_BUDGET,
        )

        first = memory.expand("Expansion", session, EXPANSION_BUDGET)
        second = memory.expand("Expansion", session, EXPANSION_BUDGET)

        self.assertLessEqual(len(first.associations), 1)
        self.assertLessEqual(len(first.history), 1)
        self.assertLessEqual(len(second.associations), 1)
        self.assertLessEqual(len(second.history), 1)
        self.assertTrue(set(a.id for a in first.associations).isdisjoint(a.id for a in second.associations))
        self.assertTrue(set(h.id for h in first.history).isdisjoint(h.id for h in second.history))
        self.assertEqual(len(first.full_descriptions), 1)
        self.assertEqual(second.full_descriptions, ())


if __name__ == "__main__":
    unittest.main()
