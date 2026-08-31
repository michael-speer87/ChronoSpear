from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from cam_protocol import parse_protocol_response
from live_quest import ProviderResult
from memory import MemorySession
from playground import INITIAL_BUDGET, PlaygroundState
from seed import build_memory
from wiretap_playground import WiretapState, activate_manual, expand_manual, send_pending


class CamProtocolTests(unittest.TestCase):
    def test_expand_command_parses_concept_with_spaces(self) -> None:
        decision = parse_protocol_response("EXPAND Historical Occurrence HISTORY")
        self.assertEqual(decision.kind, "expand")
        self.assertEqual(decision.concept, "Historical Occurrence")
        self.assertEqual(decision.channel, "HISTORY")

    def test_activate_command_parses_exact_requested_name(self) -> None:
        decision = parse_protocol_response("ACTIVATE Historical Occurrence")
        self.assertEqual(decision.kind, "activate")
        self.assertEqual(decision.concept, "Historical Occurrence")

    def test_answer_requires_evidence_line(self) -> None:
        with self.assertRaises(ValueError):
            parse_protocol_response("ANSWER: CAM remembers and the LLM reasons.")

    def test_ordinary_language_request_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_protocol_response("Could you tell me more about Expansion history?")

    def test_old_request_more_dialect_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_protocol_response("REQUEST_MORE: Expansion")


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

    def send_fake(self, state: WiretapState, text: str) -> None:
        fake = ProviderResult(text, {"prompt_tokens": 10, "completion_tokens": 3})
        with patch("wiretap_playground.call_provider", return_value=fake):
            with redirect_stdout(io.StringIO()):
                send_pending(state)

    def test_llm_expand_request_is_not_auto_executed(self) -> None:
        state = self.make_state()
        initial_seen_history = set(state.playground.session.seen_history)

        self.send_fake(state, "EXPAND Expansion HISTORY")

        self.assertIsNone(state.pending_packet)
        self.assertEqual(state.last_response, "EXPAND Expansion HISTORY")
        self.assertIsNotNone(state.last_decision)
        assert state.last_decision is not None
        self.assertEqual(state.last_decision.kind, "expand")
        self.assertEqual(state.playground.session.seen_history, initial_seen_history)
        self.assertEqual(state.playground.expansion_count, 0)

    def test_human_history_expansion_creates_pending_history_only_delta(self) -> None:
        state = self.make_state()
        self.send_fake(state, "EXPAND Expansion HISTORY")

        message_count_before = len(state.messages)
        with redirect_stdout(io.StringIO()):
            expand_manual(state, "Expansion HISTORY")

        self.assertIsNotNone(state.pending_packet)
        assert state.pending_packet is not None
        self.assertEqual(state.playground.expansion_count, 1)
        self.assertEqual(len(state.messages), message_count_before)
        self.assertEqual(state.pending_packet.associations, ())
        self.assertEqual(state.pending_packet.full_descriptions, ())
        self.assertLessEqual(len(state.pending_packet.history), 1)

    def test_human_association_expansion_does_not_bundle_history_or_description(self) -> None:
        state = self.make_state()
        self.send_fake(state, "EXPAND Expansion ASSOCIATIONS")

        with redirect_stdout(io.StringIO()):
            expand_manual(state, "Expansion ASSOCIATIONS")

        self.assertIsNotNone(state.pending_packet)
        assert state.pending_packet is not None
        self.assertEqual(state.pending_packet.history, ())
        self.assertEqual(state.pending_packet.full_descriptions, ())
        self.assertLessEqual(len(state.pending_packet.associations), 1)

    def test_description_channel_sends_description_only_once(self) -> None:
        state = self.make_state()
        self.send_fake(state, "EXPAND Expansion DESCRIPTION")

        with redirect_stdout(io.StringIO()):
            expand_manual(state, "Expansion DESCRIPTION")

        self.assertIsNotNone(state.pending_packet)
        assert state.pending_packet is not None
        self.assertEqual(len(state.pending_packet.full_descriptions), 1)
        self.assertEqual(state.pending_packet.associations, ())
        self.assertEqual(state.pending_packet.history, ())

    def test_exact_activation_can_surface_new_named_concept(self) -> None:
        state = self.make_state()
        self.send_fake(state, "ACTIVATE Historical Occurrence")

        self.assertNotIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        with redirect_stdout(io.StringIO()):
            activate_manual(state, "Historical Occurrence")

        self.assertIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        self.assertIsNotNone(state.pending_packet)
        assert state.pending_packet is not None
        self.assertTrue(any(c.name == "Historical Occurrence" for c in state.pending_packet.new_synopses))

    def test_misspelled_activation_does_not_guess(self) -> None:
        state = self.make_state()
        self.send_fake(state, "ACTIVATE Historical Occurence")

        with redirect_stdout(io.StringIO()):
            activate_manual(state, "Historical Occurence")

        self.assertNotIn("Historical Occurrence", state.playground.session.surfaced_concepts)
        self.assertIsNone(state.pending_packet)

    def test_protocol_violation_does_not_create_a_cam_action(self) -> None:
        state = self.make_state()
        self.send_fake(state, "Tell me more about Expansion history.")

        self.assertIsNone(state.pending_packet)
        self.assertIsNone(state.last_decision)
        self.assertEqual(state.playground.expansion_count, 0)


if __name__ == "__main__":
    unittest.main()
