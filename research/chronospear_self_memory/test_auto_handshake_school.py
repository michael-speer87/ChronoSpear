from __future__ import annotations

import unittest

import auto_handshake as base
import auto_handshake_school as school


class CamSchoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_prompt = base.WIRETAP_SYSTEM_PROMPT

    def tearDown(self) -> None:
        base.WIRETAP_SYSTEM_PROMPT = self.original_prompt

    def test_curriculum_uses_only_synthetic_evidence_ids(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertNotIn("o-083", text)
        self.assertNotIn("a-expand", text)
        self.assertNotIn("a-lang", text)
        self.assertNotIn("a-mcp", text)

    def test_install_school_prompt_is_idempotent(self) -> None:
        school.install_school_prompt()
        once = base.WIRETAP_SYSTEM_PROMPT
        school.install_school_prompt()
        twice = base.WIRETAP_SYSTEM_PROMPT

        self.assertEqual(once, twice)
        self.assertEqual(
            once.count("CAM SCHOOL V2: SYNTHETIC EVIDENCE-SUFFICIENCY AND MEMORY-NAVIGATION EXAMPLES"),
            1,
        )
        self.assertEqual(once.count("IMPORTANT TRANSPORT RULE:"), 1)

    def test_curriculum_teaches_three_sufficiency_states_without_new_protocol_output(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("INSUFFICIENT:", text)
        self.assertIn("PARTIAL:", text)
        self.assertIn("SUFFICIENT:", text)
        self.assertIn("Do NOT output these labels", text)

    def test_curriculum_teaches_continue_when_evidence_is_only_related(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("Topic-adjacent evidence is not direct support", text)
        self.assertIn("EXPAND Beacon HISTORY", text)
        self.assertIn("Silent judgment: PARTIAL", text)

    def test_curriculum_teaches_stop_even_when_more_memory_exists(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("DIRECT EVIDENCE MEANS STOP, EVEN WHEN MORE MEMORY EXISTS", text)
        self.assertIn("Memory being available is NOT a reason to retrieve it", text)
        self.assertIn("Stop retrieving as soon as the material uncertainty is resolved", text)
        self.assertIn("Silent judgment: SUFFICIENT", text)

    def test_curriculum_teaches_narrow_missing_fact_policy(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("identify what material fact is missing", text)
        self.assertIn("request the smallest CAM channel likely to supply that fact", text)
        self.assertIn('"What material claim can I not support yet?"', text)

    def test_curriculum_preserves_hypothesis_state(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("HYPOTHESIS is not a decision", text)
        self.assertIn("it remains a hypothesis rather than an established policy change", text)


if __name__ == "__main__":
    unittest.main()
