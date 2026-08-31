from __future__ import annotations

import unittest

from experiment import (
    ActivatedObject,
    DecisionKind,
    InitialPacketBuilder,
    LlmDecision,
    PacketBudget,
    PacketSource,
    ReasoningHarness,
    ScriptedExpansionProvider,
    ScriptedProvider,
)


class MinimumFirstPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = InitialPacketBuilder(
            PacketBudget(recent_chat=2, recent_history=3, effective_associations=2)
        )
        self.common = dict(
            perspective="Dorf",
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

    def test_question_wording_does_not_change_memory_selection(self) -> None:
        where_packet = self.builder.build(
            PacketSource(latest_interaction="Where is Alric?", **self.common)
        )
        faction_packet = self.builder.build(
            PacketSource(latest_interaction="Who does Alric work for?", **self.common)
        )

        self.assertNotEqual(where_packet.latest_interaction, faction_packet.latest_interaction)
        self.assertEqual(where_packet.memory_fingerprint(), faction_packet.memory_fingerprint())

    def test_fixed_budgets_take_recent_tail_only(self) -> None:
        packet = self.builder.build(PacketSource(latest_interaction="Where is Alric?", **self.common))

        self.assertEqual(
            packet.recent_history,
            (
                "WT110: Alric ordered an ale.",
                "WT120: Alric spoke with Elara by the fireplace.",
                "WT130: Dorf left the Black Stag.",
            ),
        )
        self.assertEqual(
            packet.effective_associations,
            (
                "Royal Guard BASED_IN Stonebridge",
                "Stonebridge PART_OF Northmarch",
            ),
        )

    def test_taxation_is_visible(self) -> None:
        packet = self.builder.build(PacketSource(latest_interaction="Where is Alric?", **self.common))

        self.assertEqual(packet.taxation.chat_items, 2)
        self.assertEqual(packet.taxation.history_items, 3)
        self.assertEqual(packet.taxation.association_items, 2)
        self.assertEqual(packet.taxation.activated_objects, 1)
        self.assertGreater(packet.taxation.characters, 0)
        self.assertGreater(packet.taxation.estimated_tokens, 0)

    def test_model_can_request_more_memory_then_answer(self) -> None:
        packet = self.builder.build(PacketSource(latest_interaction="Where is Alric?", **self.common))
        provider = ScriptedProvider(
            (
                LlmDecision(
                    DecisionKind.REQUEST_MORE,
                    "Give me any later history involving Alric after he spoke with Elara.",
                ),
                LlmDecision(
                    DecisionKind.ANSWER,
                    "Alric was last known to be in the Black Stag.",
                ),
            )
        )
        expansion = ScriptedExpansionProvider(
            "No later known occurrence records Alric leaving the Black Stag."
        )

        result = ReasoningHarness(provider, expansion).run(packet)

        self.assertEqual(result.provider_calls, 2)
        self.assertEqual(
            result.expansion_request,
            "Give me any later history involving Alric after he spoke with Elara.",
        )
        self.assertEqual(expansion.requests, [result.expansion_request])
        self.assertEqual(result.final_decision.kind, DecisionKind.ANSWER)
        self.assertIn("ADDITIONAL MEMORY", provider.seen_packets[1])

    def test_blank_expansion_request_is_rejected(self) -> None:
        packet = self.builder.build(PacketSource(latest_interaction="Where is Alric?", **self.common))
        provider = ScriptedProvider((LlmDecision(DecisionKind.REQUEST_MORE, "   "),))
        expansion = ScriptedExpansionProvider("unused")

        with self.assertRaises(ValueError):
            ReasoningHarness(provider, expansion).run(packet)


if __name__ == "__main__":
    unittest.main()
