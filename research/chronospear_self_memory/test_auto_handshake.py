from __future__ import annotations

import unittest

from live_quest import ProviderResult
from auto_handshake import run_question


class FakeProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def __call__(self, messages: list[dict[str, str]]) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            next(self.responses),
            {"prompt_tokens": 10, "completion_tokens": 3},
        )


class AutoHandshakeTests(unittest.TestCase):
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
