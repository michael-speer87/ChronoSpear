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


TRAIN_FIRST = {"Amber", "Copper", "Ivory", "Moss", "Silver", "Cinder", "Willow", "Echo"}
TRAIN_SECOND = {"Beacon", "Relay", "Archive", "Ledger", "Harbor", "Workshop", "Tower", "Project"}
EVAL_FIRST = {"Quartz", "Juniper", "Obsidian", "Saffron", "Violet", "Marble", "Cobalt", "Birch"}
EVAL_SECOND = {"Observatory", "Caravan", "Citadel", "Registry", "Foundry", "Library", "Gateway", "Station"}


def surfaced_concepts(examples) -> list[str]:
    concepts: list[str] = []
    marker = "Currently surfaced concepts:\n"
    end_marker = "\n\nValid EXPAND commands right now:"
    for example in examples:
        user_text = example.messages[1]["content"]
        section = user_text.split(marker, 1)[1].split(end_marker, 1)[0]
        concepts.extend(
            line[2:].strip()
            for line in section.splitlines()
            if line.startswith("- ") and line != "- none"
        )
    return concepts


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

    def test_eval_uses_distinct_generated_concept_vocabulary(self) -> None:
        train = build_examples("train", 8, 417)
        eval_set = build_examples("eval", 8, 418)

        self.assertTrue(TRAIN_FIRST.isdisjoint(EVAL_FIRST))
        self.assertTrue(TRAIN_SECOND.isdisjoint(EVAL_SECOND))

        train_concepts = surfaced_concepts(train)
        eval_concepts = surfaced_concepts(eval_set)
        self.assertTrue(train_concepts)
        self.assertTrue(eval_concepts)

        for concept in train_concepts:
            first, second, _number = concept.split()
            self.assertIn(first, TRAIN_FIRST)
            self.assertIn(second, TRAIN_SECOND)
            self.assertNotIn(first, EVAL_FIRST)
            self.assertNotIn(second, EVAL_SECOND)

        for concept in eval_concepts:
            first, second, _number = concept.split()
            self.assertIn(first, EVAL_FIRST)
            self.assertIn(second, EVAL_SECOND)
            self.assertNotIn(first, TRAIN_FIRST)
            self.assertNotIn(second, TRAIN_SECOND)

    def test_native_prompt_is_compact_and_forbids_visible_reasoning(self) -> None:
        self.assertLess(len(CAM_NATIVE_SYSTEM_PROMPT), 1400)
        self.assertIn("every material claim must have direct support", CAM_NATIVE_SYSTEM_PROMPT)
        self.assertIn("Available memory is not itself a reason", CAM_NATIVE_SYSTEM_PROMPT)
        self.assertIn("Never output analysis", CAM_NATIVE_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
