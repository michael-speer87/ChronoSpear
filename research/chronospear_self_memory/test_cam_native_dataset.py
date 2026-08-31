from __future__ import annotations

import json
import unittest

from cam_native_dataset import (
    BUILDERS,
    CAM_NATIVE_SYSTEM_PROMPT,
    TRAIN_FORBIDDEN,
    build_examples,
    validate_no_benchmark_leak,
)
from cam_protocol import parse_protocol_response


class CamNativeDatasetTests(unittest.TestCase):
    def test_builds_one_example_per_skill_per_variant(self) -> None:
        examples = build_examples("train", variants_per_skill=3, seed=417)
        self.assertEqual(len(examples), len(BUILDERS) * 3)
        self.assertEqual(len({example.skill for example in examples}), len(BUILDERS))

    def test_every_training_target_is_valid_cam_protocol(self) -> None:
        examples = build_examples("train", variants_per_skill=2, seed=417)
        for example in examples:
            target = example.messages[-1]["content"]
            with self.subTest(skill=example.skill, target=target):
                parse_protocol_response(target)

    def test_training_data_contains_no_real_benchmark_text(self) -> None:
        examples = build_examples("train", variants_per_skill=4, seed=417)
        validate_no_benchmark_leak(examples)
        text = json.dumps([example.to_json() for example in examples])
        for forbidden in TRAIN_FORBIDDEN:
            self.assertNotIn(forbidden, text)

    def test_eval_uses_distinct_name_vocabulary(self) -> None:
        train = json.dumps([example.to_json() for example in build_examples("train", 2, 417)])
        eval_text = json.dumps([example.to_json() for example in build_examples("eval", 2, 418)])
        self.assertIn("Amber", train + " Copper")
        self.assertNotIn("Quartz", train)
        self.assertIn("Quartz", eval_text + " Quartz")
        self.assertNotIn("Amber Beacon", eval_text)

    def test_native_prompt_is_compact_and_forbids_visible_reasoning(self) -> None:
        self.assertLess(len(CAM_NATIVE_SYSTEM_PROMPT), 1400)
        self.assertIn("every material claim must have direct support", CAM_NATIVE_SYSTEM_PROMPT)
        self.assertIn("Available memory is not itself a reason", CAM_NATIVE_SYSTEM_PROMPT)
        self.assertIn("Never output analysis", CAM_NATIVE_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
