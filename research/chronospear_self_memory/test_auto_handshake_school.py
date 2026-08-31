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
        self.assertNotIn("ChronoSpear benchmark answers", text.split("These examples", 1)[-1])

    def test_install_school_prompt_is_idempotent(self) -> None:
        school.install_school_prompt()
        once = base.WIRETAP_SYSTEM_PROMPT
        school.install_school_prompt()
        twice = base.WIRETAP_SYSTEM_PROMPT

        self.assertEqual(once, twice)
        self.assertEqual(once.count("CAM SCHOOL: SYNTHETIC MEMORY-NAVIGATION EXAMPLES"), 1)
        self.assertEqual(once.count("IMPORTANT TRANSPORT RULE:"), 1)

    def test_curriculum_teaches_continue_when_evidence_is_only_related(self) -> None:
        text = school.CAM_SCHOOL_CURRICULUM
        self.assertIn("Topic-adjacent evidence is not the same as direct support", text)
        self.assertIn("EXPAND Beacon HISTORY", text)
        self.assertIn("HYPOTHESIS is not a decision", text)


if __name__ == "__main__":
    unittest.main()
