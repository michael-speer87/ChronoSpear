from __future__ import annotations

import json
import unittest

from cam_native_dataset import TRAIN_FORBIDDEN
from cam_native_dataset_v2 import (
    CAM_NATIVE_SYSTEM_PROMPT_V2,
    EXCLUDED_V1_SKILLS,
    TRAJECTORY_BUILDERS,
    build_v2_examples,
)
from cam_protocol import parse_protocol_response


class CamNativeDatasetV2Tests(unittest.TestCase):
    def test_v2_contains_multi_turn_trajectories(self) -> None:
        examples = build_v2_examples(
            "train",
            foundation_per_skill=1,
            trajectory_per_skill=1,
            seed=417,
        )
        trajectories = [example for example in examples if example.skill.startswith("trajectory_")]
        self.assertEqual(len(trajectories), len(TRAJECTORY_BUILDERS))
        self.assertTrue(all(sum(m["role"] == "assistant" for m in e.messages) >= 2 for e in trajectories))

    def test_bad_description_stop_skill_is_not_in_v2(self) -> None:
        examples = build_v2_examples(
            "train",
            foundation_per_skill=2,
            trajectory_per_skill=1,
            seed=417,
        )
        skills = {example.skill for example in examples}
        self.assertTrue(EXCLUDED_V1_SKILLS.isdisjoint(skills))

    def test_every_assistant_turn_is_valid_cam_protocol(self) -> None:
        examples = build_v2_examples(
            "train",
            foundation_per_skill=1,
            trajectory_per_skill=1,
            seed=417,
        )
        for example in examples:
            for message in example.messages:
                if message["role"] != "assistant":
                    continue
                with self.subTest(skill=example.skill, target=message["content"]):
                    parse_protocol_response(message["content"])

    def test_trajectory_user_turns_use_real_cam_packet_surface(self) -> None:
        examples = build_v2_examples(
            "train",
            foundation_per_skill=1,
            trajectory_per_skill=1,
            seed=417,
        )
        trajectories = [example for example in examples if example.skill.startswith("trajectory_")]
        for example in trajectories:
            for message in example.messages:
                if message["role"] != "user":
                    continue
                self.assertIn("CHRONOSPEAR DESIGN MEMORY PACKET", message["content"])
                self.assertIn("CAM CONTROL SURFACE", message["content"])

    def test_v2_contains_no_real_benchmark_text(self) -> None:
        examples = build_v2_examples(
            "train",
            foundation_per_skill=2,
            trajectory_per_skill=2,
            seed=417,
        )
        text = json.dumps([example.to_json() for example in examples])
        for forbidden in TRAIN_FORBIDDEN:
            self.assertNotIn(forbidden, text)

    def test_v2_prompt_explicitly_separates_description_from_event_evidence(self) -> None:
        self.assertIn("Descriptions clarify identity", CAM_NATIVE_SYSTEM_PROMPT_V2)
        self.assertIn("Never repeat a memory command", CAM_NATIVE_SYSTEM_PROMPT_V2)
        self.assertIn("Do not use EVIDENCE: none for a factual answer", CAM_NATIVE_SYSTEM_PROMPT_V2)
        self.assertLess(len(CAM_NATIVE_SYSTEM_PROMPT_V2), 1800)


if __name__ == "__main__":
    unittest.main()
