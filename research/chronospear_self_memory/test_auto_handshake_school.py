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
            once.count("CAM SCHOOL V2.1: SYNTHETIC EVIDENCE-SUFFICIENCY AND MEMORY-NAVIGATION EXAMPLES"),
            1,
        )
        self.assertEqual(once.count("IMPORTANT TRANSPORT RULE:"), 1)

    def test_curriculum_teaches_three_sufficiency_states_as_private_reasoning(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("INSUFFICIENT:", text)
        self.assertIn("PARTIAL:", text)
        self.assertIn("SUFFICIENT:", text)
        self.assertIn("Your internal evidence-sufficiency reasoning is private", text)
        self.assertIn("Never expose this check in the visible response", text)

    def test_curriculum_has_strict_visible_output_contract(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("OUTPUT CONTRACT", text)
        self.assertIn("Your ENTIRE visible response must be exactly one of these protocol forms", text)
        self.assertIn("Do not add a preamble", text)
        self.assertIn("Never reveal this private check", text)
        self.assertNotIn('"What material claim can I not support yet?"', text)

    def test_curriculum_teaches_continue_when_evidence_is_only_related(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("Topic-adjacent evidence is not direct support", text)
        self.assertIn("EXPAND Beacon HISTORY", text)
        self.assertIn("Lesson annotation, private only: PARTIAL", text)

    def test_curriculum_teaches_stop_even_when_more_memory_exists(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("DIRECT EVIDENCE MEANS STOP, EVEN WHEN MORE MEMORY EXISTS", text)
        self.assertIn("Memory being available is NOT a reason to retrieve it", text)
        self.assertIn("Stop retrieving as soon as the material uncertainty is resolved", text)
        self.assertIn("Lesson annotation, private only: SUFFICIENT", text)

    def test_curriculum_teaches_narrow_missing_fact_policy(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("privately identify the unsupported material fact", text)
        self.assertIn("request the smallest CAM channel likely to supply that fact", text)
        self.assertIn("If one remains unsupported, output only the smallest useful CAM memory request", text)

    def test_curriculum_preserves_hypothesis_state(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("HYPOTHESIS is not a decision", text)
        self.assertIn("it remains a hypothesis rather than an established policy change", text)


if __name__ == "__main__":
    unittest.main()
