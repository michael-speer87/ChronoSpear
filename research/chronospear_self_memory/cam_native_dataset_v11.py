from __future__ import annotations

import argparse
from pathlib import Path
import random
from typing import Callable

from cam_native_dataset import (
    CAM_NATIVE_SYSTEM_PROMPT,
    Example,
    _concept,
    _example,
    _group,
    _packet,
    _person,
    build_examples as build_v1_examples,
    validate_no_benchmark_leak,
    write_jsonl,
)


# V1.1 is deliberately an additive control, not a replacement curriculum.
# Every V1 example remains unchanged. These examples add only CAM ontology
# literacy: what each memory surface can directly support and when a nearby
# memory is context rather than the strongest evidence.


def synopsis_orients_history_required(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    question = rng.choice(
        [
            f"What failure happened during the {concept} trial?",
            f"What outcome did the {concept} experiment produce?",
        ]
    )
    evidence = [
        f"SYNOPSIS {concept}: a bounded retrieval experiment involving {person}."
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
        f"EXPAND {concept} DESCRIPTION",
    ]
    return _example(
        "ontology_synopsis_orients_not_event_proof",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        f"EXPAND {concept} HISTORY",
    )


def description_not_event_proof(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    question = rng.choice(
        [
            f"What happened when {concept} was deployed?",
            f"What did the latest {concept} trial discover?",
        ]
    )
    evidence = [
        f"DESCRIPTION {concept}: a deterministic relay that sends bounded memory pages."
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
    ]
    return _example(
        "ontology_description_defines_not_event_proof",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        f"EXPAND {concept} HISTORY",
    )


def description_direct_identity(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    history_id = f"ont-{split}-desc-{index}-h1"
    question = rng.choice(
        [
            f"What is {concept}?",
            f"How is {concept} defined?",
        ]
    )
    evidence = [
        f"DESCRIPTION {concept}: an enduring addressable identity used to anchor bounded recall.",
        f"[{history_id}] 2026-02-04 [experimentally_proven] {person} inspected {concept} during an unrelated retrieval timing probe.",
    ]
    commands = [f"EXPAND {concept} ASSOCIATIONS"]
    answer = (
        f"ANSWER: {concept} is an enduring addressable identity used to anchor bounded recall.\n"
        "EVIDENCE: none"
    )
    return _example(
        "ontology_description_direct_for_identity",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def association_direct_relationship(rng: random.Random, split: str, index: int) -> Example:
    left = _concept(rng, split)
    right = _concept(rng, split)
    relationship = rng.choice(["FEEDS", "DEPENDS_ON", "MEMBER_OF", "SUPPORTS"])
    association_id = f"ont-{split}-assoc-{index}-a1"
    history_id = f"ont-{split}-assoc-{index}-h1"
    question = rng.choice(
        [
            f"What relationship currently connects {left} to {right}?",
            f"How is {left} associated with {right}?",
        ]
    )
    evidence = [
        f"[{association_id}] [experimentally_proven] {left} {relationship} {right}",
        f"[{history_id}] 2026-02-11 [experimentally_proven] A probe inspected {left} and {right} while validating retrieval behavior.",
    ]
    commands = [
        f"EXPAND {left} HISTORY",
        f"EXPAND {right} HISTORY",
    ]
    answer = (
        f"ANSWER: {left} {relationship} {right}.\n"
        f"EVIDENCE: {association_id}"
    )
    return _example(
        "ontology_association_direct_for_relationship",
        _packet(question=question, evidence=evidence, surfaced=[left, right], commands=commands),
        answer,
    )


def history_direct_event(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    history_id = f"ont-{split}-event-{index}-h1"
    association_id = f"ont-{split}-event-{index}-a1"
    failure = rng.choice(
        [
            "a stale page index caused the same memory page to be requested twice",
            "eager widening admitted unrelated neighbors into the working set",
            "an expired alias remained visible after the canonical identity changed",
        ]
    )
    question = rng.choice(
        [
            f"What failure did the {concept} experiment expose?",
            f"What happened in the failed {concept} trial?",
        ]
    )
    evidence = [
        f"DESCRIPTION {concept}: a bounded retrieval strategy under evaluation.",
        f"[{association_id}] [locked] {concept} HAS_MODE BOUNDED_RETRIEVAL",
        f"[{history_id}] 2026-03-08 [experimentally_proven] The {concept} trial exposed that {failure}.",
    ]
    commands = [f"EXPAND {concept} ASSOCIATIONS"]
    answer = (
        f"ANSWER: The experiment exposed that {failure}.\n"
        f"EVIDENCE: {history_id}"
    )
    return _example(
        "ontology_history_direct_for_event",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def history_direct_for_change(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    association_id = f"ont-{split}-change-{index}-a1"
    history_id = f"ont-{split}-change-{index}-h1"
    old_mode, new_mode = rng.choice(
        [
            ("FULL_SNAPSHOT", "DELTA_PAGE"),
            ("EAGER_LOAD", "LAZY_LOAD"),
            ("GLOBAL_SCAN", "BOUNDED_PAGE"),
        ]
    )
    question = f"What changed in {concept}?"
    evidence = [
        f"[{association_id}] [locked] {concept} USES_MODE {new_mode}",
        f"[{history_id}] 2026-04-17 [experimentally_proven] {concept} changed from {old_mode} to {new_mode} after the earlier mode dominated retrieval cost.",
    ]
    commands = [f"EXPAND {concept} DESCRIPTION"]
    answer = (
        f"ANSWER: {concept} changed from {old_mode} to {new_mode}.\n"
        f"EVIDENCE: {history_id}"
    )
    return _example(
        "ontology_history_direct_for_change",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def direct_association_beats_related_history(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    group = _group(rng)
    association_id = f"ont-{split}-direct-{index}-a1"
    history_id = f"ont-{split}-direct-{index}-h1"
    supported_use = rng.choice(
        [
            "reuse one cache entry across equivalent aliases",
            "answer relation queries from a bounded opening neighborhood",
            "keep a stable identity key while descriptions are amended",
        ]
    )
    question = f"What use is currently supported for {concept}?"
    evidence = [
        f"[{history_id}] 2026-05-09 [experimentally_proven] A widening probe involving {concept} surfaced {group} and motivated a follow-up capability test.",
        f"[{association_id}] [experimentally_proven] {concept} SUPPORTED_USE {supported_use}",
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
    ]
    answer = (
        f"ANSWER: {concept} supports the use: {supported_use}.\n"
        f"EVIDENCE: {association_id}"
    )
    return _example(
        "ontology_direct_support_beats_related_context",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


ONTOLOGY_BUILDERS: tuple[Callable[[random.Random, str, int], Example], ...] = (
    synopsis_orients_history_required,
    description_not_event_proof,
    description_direct_identity,
    association_direct_relationship,
    history_direct_event,
    history_direct_for_change,
    direct_association_beats_related_history,
)


def build_examples(
    split: str,
    *,
    base_variants_per_skill: int,
    ontology_variants_per_skill: int,
    seed: int,
) -> list[Example]:
    if split not in {"train", "eval"}:
        raise ValueError("split must be train or eval")
    if base_variants_per_skill < 1:
        raise ValueError("base_variants_per_skill must be positive")
    if ontology_variants_per_skill < 1:
        raise ValueError("ontology_variants_per_skill must be positive")

    # Preserve the exact V1 curriculum and its random stream.
    examples = list(build_v1_examples(split, base_variants_per_skill, seed))

    # Keep ontology generation on a separate random stream so adding/removing one
    # literacy skill cannot perturb the original V1 examples.
    ontology_rng = random.Random(seed + 1100)
    for builder in ONTOLOGY_BUILDERS:
        for index in range(ontology_variants_per_skill):
            examples.append(builder(ontology_rng, split, index))

    random.Random(seed + 2200).shuffle(examples)
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build V1.1 CAM-native SFT data: unchanged V1 behavior plus a small CAM ontology-literacy curriculum."
    )
    parser.add_argument("--output-dir", default="cam_native_data_v11")
    parser.add_argument("--base-train-per-skill", type=int, default=64)
    parser.add_argument("--base-eval-per-skill", type=int, default=16)
    parser.add_argument("--ontology-train-per-skill", type=int, default=16)
    parser.add_argument("--ontology-eval-per-skill", type=int, default=8)
    parser.add_argument("--seed", type=int, default=417)
    args = parser.parse_args()

    train = build_examples(
        "train",
        base_variants_per_skill=args.base_train_per_skill,
        ontology_variants_per_skill=args.ontology_train_per_skill,
        seed=args.seed,
    )
    eval_set = build_examples(
        "eval",
        base_variants_per_skill=args.base_eval_per_skill,
        ontology_variants_per_skill=args.ontology_eval_per_skill,
        seed=args.seed + 1,
    )
    validate_no_benchmark_leak(train)
    validate_no_benchmark_leak(eval_set)

    output = Path(args.output_dir)
    write_jsonl(output / "train.jsonl", train)
    write_jsonl(output / "eval.jsonl", eval_set)

    base_train_count = 11 * args.base_train_per_skill
    ontology_train_count = len(ONTOLOGY_BUILDERS) * args.ontology_train_per_skill
    print(f"train_examples={len(train)}")
    print(f"eval_examples={len(eval_set)}")
    print(f"v1_base_train_examples={base_train_count}")
    print(f"ontology_train_examples={ontology_train_count}")
    print(f"ontology_fraction={ontology_train_count / len(train):.1%}")
    print(f"ontology_skills={len(ONTOLOGY_BUILDERS)}")
    print(f"system_prompt_characters={len(CAM_NATIVE_SYSTEM_PROMPT)}")
    print(f"output_dir={output.resolve()}")


if __name__ == "__main__":
    main()
