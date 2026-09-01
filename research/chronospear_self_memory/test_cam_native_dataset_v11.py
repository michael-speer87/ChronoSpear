from __future__ import annotations

import json
import unittest

from cam_native_dataset import (
    CAM_NATIVE_SYSTEM_PROMPT,
    build_examples as build_v1_examples,
    validate_no_benchmark_leak,
)
from cam_native_dataset_v11 import ONTOLOGY_BUILDERS, build_examples
from cam_protocol import parse_protocol_response


class CamNativeDatasetV11Tests(unittest.TestCase):
    def test_preserves_every_v1_example_unchanged(self) -> None:
        base = build_v1_examples("train", variants_per_skill=3, seed=417)
        v11 = build_examples(
            "train",
            base_variants_per_skill=3,
            ontology_variants_per_skill=2,
            seed=417,
        )

        base_json = {json.dumps(example.to_json(), sort_keys=True) for example in base}
        v11_json = {json.dumps(example.to_json(), sort_keys=True) for example in v11}
        self.assertTrue(base_json.issubset(v11_json))

    def test_adds_only_the_expected_ontology_examples(self) -> None:
        base_variants = 3
        ontology_variants = 2
        examples = build_examples(
            "train",
            base_variants_per_skill=base_variants,
            ontology_variants_per_skill=ontology_variants,
            seed=417,
        )
        expected = 11 * base_variants + len(ONTOLOGY_BUILDERS) * ontology_variants
        self.assertEqual(len(examples), expected)

        ontology_skills = {example.skill for example in examples if example.skill.startswith("ontology_")}
        self.assertEqual(len(ontology_skills), len(ONTOLOGY_BUILDERS))

    def test_every_target_remains_valid_cam_protocol(self) -> None:
        examples = build_examples(
            "train",
            base_variants_per_skill=2,
            ontology_variants_per_skill=2,
            seed=417,
        )
        for example in examples:
            target = example.messages[-1]["content"]
            with self.subTest(skill=example.skill, target=target):
                parse_protocol_response(target)

    def test_ontology_examples_keep_the_compact_v1_runtime_contract(self) -> None:
        examples = build_examples(
            "train",
            base_variants_per_skill=1,
            ontology_variants_per_skill=2,
            seed=417,
        )
        ontology_examples = [example for example in examples if example.skill.startswith("ontology_")]
        self.assertTrue(ontology_examples)
        for example in ontology_examples:
            self.assertEqual(example.messages[0]["content"], CAM_NATIVE_SYSTEM_PROMPT)

    def test_ontology_curriculum_contains_all_memory_semantic_roles(self) -> None:
        examples = build_examples(
            "train",
            base_variants_per_skill=1,
            ontology_variants_per_skill=2,
            seed=417,
        )
        ontology_text = json.dumps(
            [example.to_json() for example in examples if example.skill.startswith("ontology_")]
        )
        self.assertIn("SYNOPSIS", ontology_text)
        self.assertIn("DESCRIPTION", ontology_text)
        self.assertIn("ASSOCIATIONS", ontology_text)
        self.assertIn("HISTORY", ontology_text)
        self.assertIn("EVIDENCE:", ontology_text)

    def test_no_real_benchmark_text_leaks_into_v11(self) -> None:
        examples = build_examples(
            "train",
            base_variants_per_skill=4,
            ontology_variants_per_skill=4,
            seed=417,
        )
        validate_no_benchmark_leak(examples)


if __name__ == "__main__":
    unittest.main()
