from __future__ import annotations

import unittest

from memory import EvidenceState
from memory_interface import MemoryInterface
from seed import build_memory


class MemoryInterfaceTests(unittest.TestCase):
    def test_added_concept_is_exactly_activatable(self) -> None:
        memory = build_memory()
        interface = MemoryInterface(memory)

        interface.add_concept(
            "Stonebridge",
            "A test place.",
            "A place used to test exact Language Surface activation.",
            ("Stone Bridge",),
        )

        self.assertEqual(memory.activate("Tell me about Stonebridge"), ("Stonebridge",))
        self.assertEqual(memory.activate("Tell me about Stone Bridge"), ("Stonebridge",))
        self.assertEqual(memory.activate("Tell me about StnBrdge"), ())

    def test_remove_concept_is_non_cascading_and_integrity_reports_damage(self) -> None:
        memory = build_memory()
        interface = MemoryInterface(memory)
        association_count = len(memory.associations)
        occurrence_count = len(memory.occurrences)

        removed = interface.remove_concept("Description")
        report = interface.integrity_report()

        self.assertEqual(removed.name, "Description")
        self.assertEqual(len(memory.associations), association_count)
        self.assertEqual(len(memory.occurrences), occurrence_count)
        self.assertIn("Description", report.dangling_association_sources)
        self.assertIn("Description", report.dangling_occurrence_participants)

    def test_association_can_be_added_and_removed_without_interpretation(self) -> None:
        memory = build_memory()
        interface = MemoryInterface(memory)

        interface.add_association(
            "a-test-1",
            "CAM",
            "DOES_NOT_CARE_ABOUT",
            "content meaning",
            EvidenceState.HYPOTHESIS,
            ("o-test-1",),
        )

        added = next(item for item in memory.associations if item.id == "a-test-1")
        self.assertEqual(added.target, "content meaning")
        removed = interface.remove_association("a-test-1")
        self.assertEqual(removed.id, "a-test-1")
        self.assertFalse(any(item.id == "a-test-1" for item in memory.associations))

    def test_occurrence_can_be_added_and_removed(self) -> None:
        memory = build_memory()
        interface = MemoryInterface(memory)

        interface.add_occurrence(
            "o-test-1",
            "2026-08-31",
            ("CAM", "LLM"),
            "A temporary playground occurrence.",
            EvidenceState.HYPOTHESIS,
        )

        self.assertTrue(any(item.id == "o-test-1" for item in memory.occurrences))
        removed = interface.remove_occurrence("o-test-1")
        self.assertEqual(removed.id, "o-test-1")
        self.assertFalse(any(item.id == "o-test-1" for item in memory.occurrences))


if __name__ == "__main__":
    unittest.main()
