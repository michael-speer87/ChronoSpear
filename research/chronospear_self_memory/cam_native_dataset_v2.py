from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import random
from typing import Callable

from cam_native_dataset import (
    Example,
    _concept,
    _group,
    _person,
    build_examples as build_v1_examples,
    validate_no_benchmark_leak,
    write_jsonl,
)
from cam_protocol import render_protocol_packet
from memory import (
    Concept,
    DesignMemory,
    DesignOccurrence,
    EvidenceState,
    MemorySession,
    PacketBudget,
)


CAM_NATIVE_SYSTEM_PROMPT_V2 = """You are a CAM-native reasoner.
CAM is external memory. You reason; CAM only stores and returns memory.
Use only supplied evidence. Preserve evidence-state labels exactly.
Descriptions clarify identity; they do not prove what an experiment, event, change, cause, or result exposed unless that claim is explicitly supplied as evidence.
Before ANSWER, every material factual claim must have direct support in admitted memory. Do not use EVIDENCE: none for a factual answer.
If support is missing, request the smallest currently valid CAM operation likely to resolve it.
Never repeat a memory command that the current control surface no longer lists. After CAM fulfills a request, read the new state and choose again.
Available memory is not itself a reason to retrieve more. Stop as soon as the answer is directly supported.
Visible output must be exactly one of:
ACTIVATE <exact unsurfaced concept>
EXPAND <surfaced concept> DESCRIPTION|ASSOCIATIONS|HISTORY
<command> AND <command> [up to four independent commands]
ANSWER: <concise answer>\nEVIDENCE: <comma-separated IDs>
Never output analysis, rationale, sufficiency labels, or ordinary-language memory requests."""


EXCLUDED_V1_SKILLS = {"description_support_stop_without_history"}


def _use_v2_prompt(example: Example) -> Example:
    messages = list(example.messages)
    messages[0] = {"role": "system", "content": CAM_NATIVE_SYSTEM_PROMPT_V2}
    return replace(example, messages=tuple(messages))


def _trajectory(
    *,
    skill: str,
    concept: str,
    question: str,
    description: str,
    occurrences: tuple[DesignOccurrence, ...],
    actions: tuple[str, ...],
    answer: str,
) -> Example:
    memory = DesignMemory(
        concepts=(
            Concept(
                concept,
                "A bounded CAM research mechanism under evaluation.",
                description,
            ),
        ),
        associations=(),
        occurrences=occurrences,
    )
    session = MemorySession()
    packet = memory.build_initial_packet(question, session, PacketBudget(0, 0))
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CAM_NATIVE_SYSTEM_PROMPT_V2},
        {"role": "user", "content": render_protocol_packet(packet)},
    ]

    for action in actions:
        messages.append({"role": "assistant", "content": action})
        _, channel = action.rsplit(maxsplit=1)
        packet = memory.expand_channel(concept, channel, session, page_size=1)
        messages.append({"role": "user", "content": render_protocol_packet(packet)})

    messages.append({"role": "assistant", "content": answer})
    return Example(skill=skill, messages=tuple(messages))


def description_then_history(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    group = _group(rng)
    eid = f"syn2-{split}-desc-history-{index}-1"
    question = f"Which reasoning failure was demonstrated by the {concept} probe?"
    occurrence = DesignOccurrence(
        eid,
        "2030-01-01",
        (concept,),
        f"The probe showed a reasoner strengthening {person} MEMBER_OF {group} into WORKS_FOR without direct support.",
        EvidenceState.PROVEN,
    )
    return _trajectory(
        skill="trajectory_description_then_history",
        concept=concept,
        question=question,
        description="A bounded retrieval mechanism used to reveal memory in small pages.",
        occurrences=(occurrence,),
        actions=(f"EXPAND {concept} DESCRIPTION", f"EXPAND {concept} HISTORY"),
        answer=(
            f"ANSWER: The probe demonstrated semantic overreach by strengthening MEMBER_OF into WORKS_FOR without direct support.\n"
            f"EVIDENCE: {eid}"
        ),
    )


def related_then_direct(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    group = _group(rng)
    related_id = f"syn2-{split}-related-{index}-2"
    direct_id = f"syn2-{split}-related-{index}-1"
    question = f"What semantic failure did the {concept} widening probe demonstrate?"
    related = DesignOccurrence(
        related_id,
        "2030-01-02",
        (concept,),
        f"The widening probe surfaced {person} MEMBER_OF {group}.",
        EvidenceState.PROVEN,
    )
    direct = DesignOccurrence(
        direct_id,
        "2030-01-01",
        (concept,),
        "The reasoner strengthened MEMBER_OF into WORKS_FOR and answered an employment claim without direct support.",
        EvidenceState.PROVEN,
    )
    return _trajectory(
        skill="trajectory_related_then_direct",
        concept=concept,
        question=question,
        description="A widening mechanism that reveals additional bounded memory.",
        occurrences=(related, direct),
        actions=(f"EXPAND {concept} HISTORY", f"EXPAND {concept} HISTORY"),
        answer=(
            "ANSWER: The probe demonstrated semantic overreach by strengthening MEMBER_OF into WORKS_FOR without direct support.\n"
            f"EVIDENCE: {direct_id}"
        ),
    )


def direct_first_stop(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    eid = f"syn2-{split}-direct-first-{index}-1"
    question = f"What failure was exposed by the {concept} experiment?"
    direct = DesignOccurrence(
        eid,
        "2030-01-01",
        (concept,),
        "The experiment showed a reasoner converting a weaker relation into a stronger claim without evidence.",
        EvidenceState.PROVEN,
    )
    return _trajectory(
        skill="trajectory_direct_first_stop",
        concept=concept,
        question=question,
        description="An experiment for testing bounded memory retrieval behavior.",
        occurrences=(direct,),
        actions=(f"EXPAND {concept} HISTORY",),
        answer=(
            "ANSWER: The experiment exposed semantic overreach: a weaker relation was converted into a stronger unsupported claim.\n"
            f"EVIDENCE: {eid}"
        ),
    )


def two_distractors_then_direct(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    group = _group(rng)
    first_id = f"syn2-{split}-deep-{index}-3"
    second_id = f"syn2-{split}-deep-{index}-2"
    direct_id = f"syn2-{split}-deep-{index}-1"
    question = f"Which reasoning error was established by testing {concept}?"
    first = DesignOccurrence(
        first_id,
        "2030-01-03",
        (concept,),
        f"The test surfaced {person} near {group} during a bounded retrieval pass.",
        EvidenceState.PROVEN,
    )
    second = DesignOccurrence(
        second_id,
        "2030-01-02",
        (concept,),
        "A later pass successfully returned another page of memory without duplicating the prior page.",
        EvidenceState.PROVEN,
    )
    direct = DesignOccurrence(
        direct_id,
        "2030-01-01",
        (concept,),
        "The reasoner treated a merely related fact as if it directly established the requested claim.",
        EvidenceState.PROVEN,
    )
    return _trajectory(
        skill="trajectory_two_distractors_then_direct",
        concept=concept,
        question=question,
        description="A bounded paging experiment for external memory.",
        occurrences=(first, second, direct),
        actions=(
            f"EXPAND {concept} HISTORY",
            f"EXPAND {concept} HISTORY",
            f"EXPAND {concept} HISTORY",
        ),
        answer=(
            "ANSWER: Testing established that the reasoner could mistake related evidence for direct support.\n"
            f"EVIDENCE: {direct_id}"
        ),
    )


def hypothesis_then_proven(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    hypothesis_id = f"syn2-{split}-state-{index}-2"
    proven_id = f"syn2-{split}-state-{index}-1"
    question = f"What retrieval behavior was experimentally established for {concept}?"
    hypothesis = DesignOccurrence(
        hypothesis_id,
        "2030-01-02",
        (concept,),
        "A proposal suggested that one-page retrieval might be sufficient for the task.",
        EvidenceState.HYPOTHESIS,
    )
    proven = DesignOccurrence(
        proven_id,
        "2030-01-01",
        (concept,),
        "Testing established that bounded additional pages can be requested until direct evidence is reached.",
        EvidenceState.PROVEN,
    )
    return _trajectory(
        skill="trajectory_hypothesis_then_proven",
        concept=concept,
        question=question,
        description="A bounded retrieval design under empirical evaluation.",
        occurrences=(hypothesis, proven),
        actions=(f"EXPAND {concept} HISTORY", f"EXPAND {concept} HISTORY"),
        answer=(
            "ANSWER: Testing established that bounded additional pages can be requested until direct evidence is reached.\n"
            f"EVIDENCE: {proven_id}"
        ),
    )


TRAJECTORY_BUILDERS: tuple[Callable[[random.Random, str, int], Example], ...] = (
    description_then_history,
    related_then_direct,
    direct_first_stop,
    two_distractors_then_direct,
    hypothesis_then_proven,
)


def build_v2_examples(
    split: str,
    *,
    foundation_per_skill: int,
    trajectory_per_skill: int,
    seed: int,
) -> list[Example]:
    foundations = [
        _use_v2_prompt(example)
        for example in build_v1_examples(split, foundation_per_skill, seed)
        if example.skill not in EXCLUDED_V1_SKILLS
    ]

    rng = random.Random(seed + 1000)
    trajectories: list[Example] = []
    for builder in TRAJECTORY_BUILDERS:
        for index in range(trajectory_per_skill):
            trajectories.append(builder(rng, split, index))

    examples = foundations + trajectories
    rng.shuffle(examples)
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CAM-native V2 SFT data with real multi-round CAM packet trajectories.")
    parser.add_argument("--output-dir", default="cam_native_data_v2")
    parser.add_argument("--train-foundation-per-skill", type=int, default=32)
    parser.add_argument("--train-trajectory-per-skill", type=int, default=32)
    parser.add_argument("--eval-foundation-per-skill", type=int, default=8)
    parser.add_argument("--eval-trajectory-per-skill", type=int, default=8)
    parser.add_argument("--seed", type=int, default=417)
    args = parser.parse_args()

    train = build_v2_examples(
        "train",
        foundation_per_skill=args.train_foundation_per_skill,
        trajectory_per_skill=args.train_trajectory_per_skill,
        seed=args.seed,
    )
    eval_set = build_v2_examples(
        "eval",
        foundation_per_skill=args.eval_foundation_per_skill,
        trajectory_per_skill=args.eval_trajectory_per_skill,
        seed=args.seed + 1,
    )
    validate_no_benchmark_leak(train)
    validate_no_benchmark_leak(eval_set)

    output = Path(args.output_dir)
    write_jsonl(output / "train.jsonl", train)
    write_jsonl(output / "eval.jsonl", eval_set)

    foundation_skills = {e.skill for e in train if not e.skill.startswith("trajectory_")}
    trajectory_skills = {e.skill for e in train if e.skill.startswith("trajectory_")}
    print(f"train_examples={len(train)}")
    print(f"eval_examples={len(eval_set)}")
    print(f"foundation_skills={len(foundation_skills)}")
    print(f"trajectory_skills={len(trajectory_skills)}")
    print(f"system_prompt_characters={len(CAM_NATIVE_SYSTEM_PROMPT_V2)}")
    print(f"output_dir={output.resolve()}")


if __name__ == "__main__":
    main()
