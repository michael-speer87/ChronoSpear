from __future__ import annotations

import unittest

from auto_handshake import run_question
from cam_protocol import render_protocol_packet
from live_quest import ProviderResult
from memory import MemorySession
from playground import INITIAL_BUDGET
from seed import build_memory


class FakeProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0
        self.messages_seen: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> ProviderResult:
        self.calls += 1
        self.messages_seen.append([dict(message) for message in messages])
        return ProviderResult(
            next(self.responses),
            {"prompt_tokens": 10, "completion_tokens": 3},
        )


class AutoHandshakeTests(unittest.TestCase):
    def test_initial_protocol_packet_marks_activated_concept_as_already_surfaced(self) -> None:
        memory = build_memory()
        session = MemorySession()
        packet = memory.build_initial_packet(
            "What semantic risk did Expansion expose?",
            session,
            INITIAL_BUDGET,
        )

        rendered = render_protocol_packet(packet)

        self.assertIn("Every concept listed below is ALREADY SURFACED", rendered)
        self.assertIn("- Expansion", rendered)
        self.assertIn("EXPAND Expansion DESCRIPTION", rendered)
        self.assertIn("EXPAND Expansion ASSOCIATIONS", rendered)
        self.assertIn("EXPAND Expansion HISTORY", rendered)
        self.assertIn("using AND", rendered)

    def test_expansion_commands_execute_until_answer(self) -> None:
        provider = FakeProvider(
            [
                "EXPAND Expansion HISTORY",
                "EXPAND Expansion HISTORY",
                "ANSWER: The widening test exposed semantic overreach.\nEVIDENCE: o-0831-overreach",
            ]
        )

        result = run_question(
            "What semantic risk did the Expansion experiment expose?",
            expected_support_any=frozenset({"o-0831-overreach"}),
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(result.commands["EXPAND HISTORY"], 2)
        self.assertEqual(result.commands["ANSWER"], 1)
        self.assertTrue(result.support_hit)
        self.assertGreater(result.cam_packet_estimated_tokens, 0)
        self.assertGreaterEqual(result.provider_usage_totals["prompt_tokens"], 30)
        first_user_message = provider.messages_seen[0][-1]["content"]
        self.assertIn("ALREADY SURFACED", first_user_message)
        self.assertIn("EXPAND Expansion HISTORY", first_user_message)

    def test_and_batch_combines_two_independent_description_requests(self) -> None:
        provider = FakeProvider(
            [
                "EXPAND Identity Node DESCRIPTION AND EXPAND Relationship Type DESCRIPTION",
                "ANSWER: Relationship Type is vocabulary while Identity Node is an enduring identity.\nEVIDENCE: none",
            ]
        )

        result = run_question(
            "Why is Relationship Type not an Identity Node?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(provider.calls, 2)
        self.assertEqual(result.commands["AND_BATCH"], 1)
        self.assertEqual(result.commands["EXPAND DESCRIPTION"], 2)
        self.assertEqual(result.commands["ANSWER"], 1)
        self.assertEqual(len(result.rounds[0].decision.operations), 2)  # type: ignore[union-attr]

    def test_and_batch_repeated_description_is_noop_while_history_continues(self) -> None:
        provider = FakeProvider(
            [
                "EXPAND Expansion HISTORY AND EXPAND Expansion DESCRIPTION",
                "EXPAND Expansion HISTORY AND EXPAND Expansion DESCRIPTION",
                "ANSWER: The experiment exposed semantic overreach.\nEVIDENCE: o-0831-overreach",
            ]
        )

        result = run_question(
            "What semantic risk did the Expansion experiment expose?",
            expected_support_any=frozenset({"o-0831-overreach"}),
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(result.commands["AND_BATCH"], 2)
        self.assertEqual(result.commands["EXPAND HISTORY"], 2)
        self.assertEqual(result.commands["EXPAND DESCRIPTION"], 2)
        self.assertTrue(result.support_hit)

    def test_and_batch_all_already_supplied_requests_return_empty_delta(self) -> None:
        provider = FakeProvider(
            [
                "EXPAND Identity Node DESCRIPTION AND EXPAND Relationship Type DESCRIPTION",
                "EXPAND Identity Node DESCRIPTION AND EXPAND Relationship Type DESCRIPTION",
                "ANSWER: Relationship Type is vocabulary while Identity Node is an enduring identity.\nEVIDENCE: none",
            ]
        )

        result = run_question(
            "Why is Relationship Type not an Identity Node?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(result.commands["AND_BATCH"], 2)
        second_delta = provider.messages_seen[2][-1]["content"]
        self.assertIn("New full identity descriptions:\n- none", second_delta)
        self.assertIn("CAM CONTROL SURFACE", second_delta)

    def test_and_batch_rejects_dependent_activate_then_expand(self) -> None:
        provider = FakeProvider(
            [
                "ACTIVATE Historical Occurrence AND EXPAND Historical Occurrence DESCRIPTION",
            ]
        )

        result = run_question(
            "How does Description differ from Historical Occurence?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "cam_operation_failure")
        self.assertIn("pre-batch surface", (result.error or "").casefold())
        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.commands["AND_BATCH"], 1)

    def test_exact_activation_can_recover_concept_missed_by_initial_typo(self) -> None:
        provider = FakeProvider(
            [
                "ACTIVATE Historical Occurrence",
                "EXPAND Historical Occurrence DESCRIPTION",
                "ANSWER: Description clarifies identity while a Historical Occurrence records what happened.\nEVIDENCE: none",
            ]
        )

        result = run_question(
            "How does Description differ from Historical Occurence?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "answered")
        self.assertEqual(result.commands["ACTIVATE"], 1)
        self.assertEqual(result.commands["EXPAND DESCRIPTION"], 1)
        self.assertEqual(provider.calls, 3)

    def test_reactivating_already_surfaced_concept_remains_a_hard_failure(self) -> None:
        provider = FakeProvider(["ACTIVATE Expansion"])

        result = run_question(
            "What semantic risk did Expansion expose?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "cam_operation_failure")
        self.assertIn("already surfaced", (result.error or "").casefold())
        self.assertEqual(provider.calls, 1)

    def test_old_request_more_dialect_is_protocol_failure(self) -> None:
        provider = FakeProvider(["REQUEST_MORE: Expansion"])

        result = run_question(
            "What semantic risk did Expansion expose?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "protocol_failure")
        self.assertIn("outside CAM protocol", result.error or "")
        self.assertEqual(provider.calls, 1)

    def test_unsurfaced_expand_is_rejected_by_cam(self) -> None:
        provider = FakeProvider(["EXPAND MCP HISTORY"])

        result = run_question(
            "What semantic risk did Expansion expose?",
            provider_fn=provider,
            verbose=False,
        )

        self.assertEqual(result.status, "cam_operation_failure")
        self.assertIn("unsurfaced", (result.error or "").casefold())
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
