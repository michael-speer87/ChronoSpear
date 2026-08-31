from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Callable


CAM_NATIVE_SYSTEM_PROMPT = """You are a CAM-native reasoner.
CAM is external memory. You reason; CAM only stores and returns memory.
Use only supplied evidence. Preserve evidence-state labels exactly.
Before ANSWER, every material claim must have direct support in admitted memory.
If a material claim lacks direct support, request the smallest valid CAM operation likely to resolve it.
Available memory is not itself a reason to retrieve more. Stop as soon as the answer is directly supported.
Visible output must be exactly one of:
ACTIVATE <exact unsurfaced concept>
EXPAND <surfaced concept> DESCRIPTION|ASSOCIATIONS|HISTORY
<command> AND <command> [up to four independent commands]
ANSWER: <concise answer>\nEVIDENCE: <comma-separated IDs or none>
Never output analysis, rationale, sufficiency labels, or ordinary-language memory requests."""


TRAIN_FORBIDDEN = (
    "o-083",
    "a-expand",
    "a-lang",
    "a-mcp",
    "What semantic risk did the Expansion experiment expose?",
    "How is our thinking about Expansion changing on 8/31?",
)


@dataclass(frozen=True)
class Example:
    skill: str
    messages: tuple[dict[str, str], ...]

    def to_json(self) -> dict[str, object]:
        return {
            "skill": self.skill,
            "messages": list(self.messages),
        }


def _concept(rng: random.Random, split: str) -> str:
    train_a = ["Amber", "Copper", "Ivory", "Moss", "Silver", "Cinder", "Willow", "Echo"]
    train_b = ["Beacon", "Relay", "Archive", "Ledger", "Harbor", "Workshop", "Tower", "Project"]
    eval_a = ["Quartz", "Juniper", "Obsidian", "Saffron", "Violet", "Marble", "Cobalt", "Birch"]
    eval_b = ["Observatory", "Caravan", "Citadel", "Registry", "Foundry", "Library", "Gateway", "Station"]
    first = train_a if split == "train" else eval_a
    second = train_b if split == "train" else eval_b
    return f"{rng.choice(first)} {rng.choice(second)} {rng.randrange(100, 999)}"


def _person(rng: random.Random) -> str:
    return rng.choice(["Mira", "Tovin", "Rell", "Sena", "Kellan", "Iris", "Perrin", "Noma"])


def _group(rng: random.Random) -> str:
    return rng.choice(["Lantern Guild", "River Watch", "Maple Circle", "Copper Society", "West Ward"])


def _packet(
    *,
    question: str,
    evidence: list[str],
    surfaced: list[str],
    commands: list[str],
) -> str:
    lines = [
        "QUESTION",
        question,
        "",
        "ADMITTED MEMORY",
    ]
    lines.extend(f"- {item}" for item in evidence) if evidence else lines.append("- none")
    lines.extend(
        [
            "",
            "CAM CONTROL SURFACE",
            "Currently surfaced concepts:",
        ]
    )
    lines.extend(f"- {item}" for item in surfaced) if surfaced else lines.append("- none")
    lines.extend(["", "Valid EXPAND commands right now:"])
    lines.extend(f"- {item}" for item in commands) if commands else lines.append("- none")
    return "\n".join(lines)


def _example(skill: str, user_text: str, assistant_text: str) -> Example:
    return Example(
        skill=skill,
        messages=(
            {"role": "system", "content": CAM_NATIVE_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ),
    )


def related_history(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    group = _group(rng)
    eid = f"syn-{split}-rel-{index}-1"
    question = rng.choice(
        [
            f"What failure mode did the {concept} widening test expose?",
            f"Which reasoning error was revealed by the {concept} widening probe?",
            f"What semantic failure did the {concept} experiment demonstrate?",
        ]
    )
    evidence = [
        f"{eid} [EXPERIMENTALLY_PROVEN]: The widening probe surfaced {person} MEMBER_OF {group}."
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
    ]
    return _example(
        "related_history_keep_looking",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        f"EXPAND {concept} HISTORY",
    )


def direct_stop(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    person = _person(rng)
    group = _group(rng)
    eid1 = f"syn-{split}-stop-{index}-1"
    eid2 = f"syn-{split}-stop-{index}-2"
    question = rng.choice(
        [
            f"What failure mode did the {concept} widening test expose?",
            f"Which reasoning error was revealed by the {concept} widening probe?",
        ]
    )
    evidence = [
        f"{eid1} [EXPERIMENTALLY_PROVEN]: The widening probe surfaced {person} MEMBER_OF {group}.",
        f"{eid2} [EXPERIMENTALLY_PROVEN]: The reasoner strengthened MEMBER_OF into WORKS_FOR and answered an employment claim without direct support.",
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
    ]
    answer = (
        "ANSWER: The experiment exposed semantic overreach: the reasoner strengthened MEMBER_OF into WORKS_FOR without direct support.\n"
        f"EVIDENCE: {eid2}"
    )
    return _example(
        "direct_support_stop",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def partial_two_claim(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    eid = f"syn-{split}-partial-{index}-1"
    change = rng.choice(["full snapshots to deltas", "global scans to bounded pages", "eager loading to lazy loading"])
    question = f"What changed in {concept}, and why?"
    evidence = [f"{eid} [EXPERIMENTALLY_PROVEN]: {concept} switched from {change}."]
    commands = [f"EXPAND {concept} HISTORY", f"EXPAND {concept} ASSOCIATIONS"]
    return _example(
        "partial_multi_claim_continue",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        f"EXPAND {concept} HISTORY",
    )


def complete_two_claim(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    eid1 = f"syn-{split}-complete-{index}-1"
    eid2 = f"syn-{split}-complete-{index}-2"
    question = f"What changed in {concept}, and why?"
    evidence = [
        f"{eid1} [EXPERIMENTALLY_PROVEN]: {concept} switched from full snapshots to deltas.",
        f"{eid2} [EXPERIMENTALLY_PROVEN]: The switch was made because repeated full snapshots dominated transfer cost.",
    ]
    commands = [f"EXPAND {concept} HISTORY", f"EXPAND {concept} ASSOCIATIONS"]
    answer = (
        f"ANSWER: {concept} switched from full snapshots to deltas because repeated full snapshots dominated transfer cost.\n"
        f"EVIDENCE: {eid1}, {eid2}"
    )
    return _example(
        "complete_multi_claim_stop",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def hypothesis_proposal_stop(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    eid = f"syn-{split}-hyp-{index}-1"
    question = f"What is the current proposal for bounding retrieval in {concept}?"
    evidence = [
        f"{eid} [HYPOTHESIS]: Per-action availability maps may bound later retrieval without enlarging the initial packet."
    ]
    commands = [f"EXPAND {concept} HISTORY", f"EXPAND {concept} ASSOCIATIONS"]
    answer = (
        "ANSWER: The current proposal is per-action availability maps; it remains a hypothesis rather than an established policy.\n"
        f"EVIDENCE: {eid}"
    )
    return _example(
        "hypothesis_preserve_and_stop",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        answer,
    )


def hypothesis_change_continue(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    eid = f"syn-{split}-hypchange-{index}-1"
    question = f"What retrieval policy change was adopted for {concept}?"
    evidence = [
        f"{eid} [HYPOTHESIS]: A per-action availability map may be a better retrieval policy."
    ]
    commands = [f"EXPAND {concept} HISTORY", f"EXPAND {concept} ASSOCIATIONS"]
    return _example(
        "hypothesis_is_not_adopted_change",
        _packet(question=question, evidence=evidence, surfaced=[concept], commands=commands),
        f"EXPAND {concept} HISTORY",
    )


def selective_branch(rng: random.Random, split: str, index: int) -> Example:
    concept = _concept(rng, split)
    report = _concept(rng, split)
    eid = f"syn-{split}-branch-{index}-1"
    question = f"Why was {concept} closed?"
    evidence = [
        f"{eid} [EXPERIMENTALLY_PROVEN]: {concept} was closed by order; the order says the reason is recorded in the {report} report."
    ]
    commands = [
        f"EXPAND {concept} HISTORY",
        f"EXPAND {report} HISTORY",
        f"EXPAND {concept} ASSOCIATIONS",
    ]
    return _example(
        "selective_branch_only_when_pointed",
        _packet(question=question, evidence=evidence, surfaced=[concept, report], commands=commands),
        f"EXPAND {report} HISTORY",
    )


def and_descriptions(rng: random.Random, split: str, index: int) -> Example:
    left = _concept(rng, split)
    right = _concept(rng, split)
    question = f"Why is {left} different from {right}?"
    commands = [
        f"EXPAND {left} DESCRIPTION",
        f"EXPAND {right} DESCRIPTION",
        f"EXPAND {left} HISTORY",
        f"EXPAND {right} HISTORY",
    ]
    target = f"EXPAND {left} DESCRIPTION AND EXPAND {right} DESCRIPTION"
    return _example(
        "and_two_independent_missing_definitions",
        _packet(question=question, evidence=[], surfaced=[left, right], commands=commands),
        target,
    )


def descriptions_stop(rng: random.Random, split: str, index: int) -> Example:
    left = _concept(rng, split)
    right = _concept(rng, split)
    question = f"Why is {left} different from {right}?"
    evidence = [
        f"DESCRIPTION {left}: a controlled vocabulary entry that defines relation semantics.",
        f"DESCRIPTION {right}: an enduring addressable identity in memory.",
    ]
    commands = [f"EXPAND {left} HISTORY", f"EXPAND {right} HISTORY"]
    answer = (
        f"ANSWER: {left} defines relation semantics, while {right} is an enduring addressable identity.\n"
        "EVIDENCE: none"
    )
    return _example(
        "description_support_stop_without_history",
        _packet(question=question, evidence=evidence, surfaced=[left, right], commands=commands),
        answer,
    )


def one_missing_description(rng: random.Random, split: str, index: int) -> Example:
    left = _concept(rng, split)
    right = _concept(rng, split)
    question = f"Why is {left} different from {right}?"
    evidence = [f"DESCRIPTION {left}: a controlled vocabulary entry that defines relation semantics."]
    commands = [
        f"EXPAND {right} DESCRIPTION",
        f"EXPAND {left} HISTORY",
        f"EXPAND {right} HISTORY",
    ]
    return _example(
        "retrieve_only_one_missing_definition",
        _packet(question=question, evidence=evidence, surfaced=[left, right], commands=commands),
        f"EXPAND {right} DESCRIPTION",
    )


def activate_explicit_unsurfaced(rng: random.Random, split: str, index: int) -> Example:
    target = _concept(rng, split)
    other = _concept(rng, split)
    question = f"What happened at {target}?"
    commands = [f"EXPAND {other} HISTORY"]
    user = _packet(question=question, evidence=[], surfaced=[other], commands=commands)
    return _example(
        "activate_exact_unsurfaced_concept",
        user,
        f"ACTIVATE {target}",
    )


BUILDERS: tuple[Callable[[random.Random, str, int], Example], ...] = (
    related_history,
    direct_stop,
    partial_two_claim,
    complete_two_claim,
    hypothesis_proposal_stop,
    hypothesis_change_continue,
    selective_branch,
    and_descriptions,
    descriptions_stop,
    one_missing_description,
    activate_explicit_unsurfaced,
)


def build_examples(split: str, variants_per_skill: int, seed: int) -> list[Example]:
    if split not in {"train", "eval"}:
        raise ValueError("split must be train or eval")
    if variants_per_skill < 1:
        raise ValueError("variants_per_skill must be positive")

    rng = random.Random(seed)
    examples: list[Example] = []
    for builder in BUILDERS:
        for index in range(variants_per_skill):
            examples.append(builder(rng, split, index))
    rng.shuffle(examples)
    return examples


def validate_no_benchmark_leak(examples: list[Example]) -> None:
    text = json.dumps([example.to_json() for example in examples], ensure_ascii=False)
    for forbidden in TRAIN_FORBIDDEN:
        if forbidden in text:
            raise ValueError(f"training data contains forbidden benchmark text: {forbidden}")


def write_jsonl(path: Path, examples: list[Example]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example.to_json(), ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic CAM-native conversational SFT data.")
    parser.add_argument("--output-dir", default="cam_native_data")
    parser.add_argument("--train-per-skill", type=int, default=64)
    parser.add_argument("--eval-per-skill", type=int, default=16)
    parser.add_argument("--seed", type=int, default=417)
    args = parser.parse_args()

    train = build_examples("train", args.train_per_skill, args.seed)
    eval_set = build_examples("eval", args.eval_per_skill, args.seed + 1)
    validate_no_benchmark_leak(train)
    validate_no_benchmark_leak(eval_set)

    output = Path(args.output_dir)
    write_jsonl(output / "train.jsonl", train)
    write_jsonl(output / "eval.jsonl", eval_set)

    print(f"train_examples={len(train)}")
    print(f"eval_examples={len(eval_set)}")
    print(f"skills={len(BUILDERS)}")
    print(f"system_prompt_characters={len(CAM_NATIVE_SYSTEM_PROMPT)}")
    print(f"output_dir={output.resolve()}")


if __name__ == "__main__":
    main()
