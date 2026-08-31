from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from live_quest import ProviderResult
from memory import MemorySession
from playground import INITIAL_BUDGET, PlaygroundState
from seed import build_memory
from wiretap_playground import WiretapState, activate_manual, expand_manual, send_pending


class WiretapPlaygroundTests(unittest.TestCase):
    def make_state(self) -> WiretapState:
        memory = build_memory()
        session = MemorySession()
        packet = memory.build_initial_packet(
            "What semantic risk did Expansion expose?",
            session,
            INITIAL_BUDGET,
        )
        playground = PlaygroundState(
            memory=memory,
            session=session,
            question="What semantic risk did Expansion expose?",
            last_packet=packet,
            total_estimated_tokens=packet.estimated_tokens,
        )
        return WiretapState(
            playground=playground,
            messages=[{"role": "system", "content": "test"}],
            pending_packet=packet,
        )

    def test_llm_request_is_not_auto_executed(self) -> None:
        state = self.make_state()
        initial_seen_history = set(state.playground.session.seen_history)

        fake = ProviderResult(
            "REQUEST_MORE: Expansion",
            {"prompt_tokens": 10, "completion_tokens": 3},
        )
        with patch("wiretap_playground.call_provider", return_value=fake):
            with redirect_stdout(io.StringIO()):
                send_pending(state)

        self.assertIsNone(state.pending_packet)
        self.assertEqual(state.last_response, "REQUEST_MORE: Expansion")
        self.assertEqual(state.playground.session.seen_history, initial_seen_history)
        self.assertEqual(state.playground.expansion_count, 0)

    def test_human_expansion_creates_pending_delta_but_does_not_send_it(self) -> None:
        state = self.make_state()
        fake = ProviderResult("REQUEST_MORE: Expansion", {})
        with patch("wiretap_playground.call_provider", return_value=fake):
            with redirect_stdout(io.StringIO()):
                send_pending(state)

        message_count_before = len(state.messages)
        with redirect_stdout(io.StringIO()):
            expand_manual(state, "Expansion")

        self.assertIsNotNone(state.pending_packet)
        self.assertEqual(state.playground.expansion_count, 1)
        self.assertEqual(len(state.messages), message_count_before)

    def test_exact_activation_can_surface_new_named_concept(self) -> None:
        state = self.make_state()
        fake = ProviderResult("REQUEST_MORE: Historical Occurrence", {})
        with patch("wiretap_playground.call_provider", return_value=fake):
            with redirect_stdout(io.StringIO()):
                send_pending(state)

        self.assertNotIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        with redirect_stdout(io.StringIO()):
            activate_manual(state, "Historical Occurrence")

        self.assertIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        self.assertIsNotNone(state.pending_packet)
        assert state.pending_packet is not None
        self.assertTrue(any(c.name == "Historical Occurrence" for c in state.pending_packet.new_synopses))

    def test_misspelled_activation_does_not_guess(self) -> None:
        state = self.make_state()
        fake = ProviderResult("REQUEST_MORE: Historical Occurence", {})
        with patch("wiretap_playground.call_provider", return_value=fake):
            with redirect_stdout(io.StringIO()):
                send_pending(state)

        with redirect_stdout(io.StringIO()):
            activate_manual(state, "Historical Occurence")

        self.assertNotIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        self.assertIsNone(state.pending_packet)


if __name__ == "__main__":
    unittest.main()
