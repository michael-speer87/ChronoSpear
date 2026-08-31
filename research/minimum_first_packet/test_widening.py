from __future__ import annotations

import unittest

from experiment import ActivatedObject, InitialPacketBuilder, PacketBudget, PacketSource
from widening import ExpansionBudget, FixedWideningProvider


class FixedWideningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PacketSource(
            perspective="Dorf",
            latest_interaction="Who does Alric work for?",
            activated_objects=(ActivatedObject("Alric", "A human adventurer."),),
            recent_chat=("Dorf asked about Elara.", "Dorf turned back to Alric."),
            recent_history=(
                "WT100: Alric entered the Black Stag.",
                "WT110: Alric ordered an ale.",
                "WT120: Alric spoke with Elara by the fireplace.",
                "WT130: Dorf left the Black Stag.",
            ),
            effective_associations=(
                "Alric MEMBER_OF Royal Guard",
                "Royal Guard BASED_IN Stonebridge",
                "Stonebridge PART_OF Northmarch",
            ),
        )
        self.packet = InitialPacketBuilder(
            PacketBudget(recent_chat=2, recent_history=3, effective_associations=2)
        ).build(self.source)

    def test_next_page_contains_only_omitted_association(self) -> None:
        expansion = FixedWideningProvider(
            self.source,
            self.packet,
            ExpansionBudget(recent_history=0, effective_associations=1),
        ).expand("Tell me about Alric's employer.")

        self.assertEqual(expansion.recent_history, ())
        self.assertEqual(
            expansion.effective_associations,
            ("Alric MEMBER_OF Royal Guard",),
        )
        self.assertEqual(expansion.taxation.association_items, 1)

    def test_request_wording_does_not_change_expansion_selection(self) -> None:
        provider = FixedWideningProvider(
            self.source,
            self.packet,
            ExpansionBudget(recent_history=0, effective_associations=1),
        )
        employer = provider.expand("Who employs Alric?")
        kingdom = provider.expand("What kingdom matters here?")

        self.assertNotEqual(employer.request, kingdom.request)
        self.assertEqual(employer.memory_fingerprint(), kingdom.memory_fingerprint())

    def test_blank_request_is_rejected(self) -> None:
        provider = FixedWideningProvider(self.source, self.packet)
        with self.assertRaises(ValueError):
            provider.expand("   ")


if __name__ == "__main__":
    unittest.main()
