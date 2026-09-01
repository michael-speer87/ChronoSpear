from __future__ import annotations

import unittest

import auto_handshake as handshake
from live_quest import ProviderResult
from memory import DesignMemory, EvidenceState
from memory_interface import MemoryInterface
from mini_igor_playground import configure_v1_world_handshake, empty_world


class MiniIgorPlaygroundTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_build_memory = handshake.build_memory
        self.original_execute_memory_action = handshake.execute_memory_action
        self.original_initial_budget = handshake.INITIAL_BUDGET
        self.original_system_prompt = handshake.WIRETAP_SYSTEM_PROMPT
        self.original_build_initial_packet = DesignMemory.build_initial_packet

    def tearDown(self) -> None:
        handshake.build_memory = self.original_build_memory
        handshake.execute_memory_action = self.original_execute_memory_action
        handshake.INITIAL_BUDGET = self.original_initial_budget
        handshake.WIRETAP_SYSTEM_PROMPT = self.original_system_prompt
        DesignMemory.build_initial_packet = self.original_build_initial_packet

    def test_world_starts_empty(self) -> None:
        world = empty_world()
        self.assertEqual(world.concepts, {})
        self.assertEqual(world.associations, ())
        self.assertEqual(world.occurrences, ())

    def test_ask_uses_mutated_world_not_design_seed(self) -> None:
        world = empty_world()
        interface = MemoryInterface(world)
        interface.add_concept(
            "Alric",
            "A person in the test world.",
            "Alric is an enduring character identity.",
        )
        interface.add_concept(
            "Stonebridge",
            "A place in the test world.",
            "Stonebridge is a settlement.",
        )
        interface.add_association(
            "a-alric-location",
            "Alric",
            "CURRENT_LOCATION",
            "Stonebridge",
            EvidenceState.LOCKED,
        )

        seen_messages: list[list[dict[str, str]]] = []

        def fake_provider(messages: list[dict[str, str]]) -> ProviderResult:
            seen_messages.append(list(messages))
            return ProviderResult(
                "ANSWER: Alric is currently in Stonebridge.\nEVIDENCE: a-alric-location",
                {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

        configure_v1_world_handshake(world)
        result = handshake.run_question(
            "Where is Alric?",
            provider_fn=fake_provider,
            max_rounds=2,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(result.evidence_ids, ("a-alric-location",))
        self.assertTrue(seen_messages)
        user_packet = seen_messages[0][-1]["content"]
        self.assertIn("Alric CURRENT_LOCATION Stonebridge", user_packet)
        self.assertNotIn("Packet #1 is intended to provide bounded starting evidence", user_packet)


if __name__ == "__main__":
    unittest.main()
