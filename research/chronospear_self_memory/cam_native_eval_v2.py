from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from cam_native_eval import _decision_signature, _normalized
from cam_native_provider import LocalCamNativeProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate every assistant decision checkpoint in CAM-native V2 conversations.")
    parser.add_argument("--eval", default="cam_native_data_v2/eval.jsonl")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b_v2")
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--trajectory-only", action="store_true")
    parser.add_argument("--limit-checkpoints", type=int)
    parser.add_argument("--show-failures", type=int, default=8)
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.eval).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.trajectory_only:
        rows = [row for row in rows if row["skill"].startswith("trajectory_")]

    checkpoints: list[tuple[str, int, list[dict[str, str]], str]] = []
    for row in rows:
        assistant_index = 0
        messages = row["messages"]
        for index, message in enumerate(messages):
            if message["role"] != "assistant":
                continue
            assistant_index += 1
            checkpoints.append((row["skill"], assistant_index, messages[:index], message["content"]))

    if args.limit_checkpoints is not None:
        checkpoints = checkpoints[: args.limit_checkpoints]

    provider = LocalCamNativeProvider(
        model_name=args.model,
        adapter_path=None if args.base_only else args.adapter,
    )

    total = 0
    protocol_valid = 0
    signature_correct = 0
    exact = 0
    skill_total: Counter[str] = Counter()
    skill_correct: Counter[str] = Counter()
    failures: list[tuple[str, int, str, str]] = []

    for skill, stage, prompt_messages, target in checkpoints:
        output = provider(prompt_messages).text
        total += 1
        skill_total[skill] += 1

        if _normalized(output) == _normalized(target):
            exact += 1

        try:
            target_signature = _decision_signature(target)
            output_signature = _decision_signature(output)
            protocol_valid += 1
            if output_signature == target_signature:
                signature_correct += 1
                skill_correct[skill] += 1
            elif len(failures) < args.show_failures:
                failures.append((skill, stage, target, output))
        except ValueError:
            if len(failures) < args.show_failures:
                failures.append((skill, stage, target, output))

    print("CAM-NATIVE V2 CHECKPOINT EVAL")
    print(f"model={args.model}")
    print(f"adapter={'none/base-only' if args.base_only else args.adapter}")
    print(f"checkpoints={total}")
    if total:
        print(f"protocol_valid={protocol_valid}/{total} ({protocol_valid / total:.1%})")
        print(f"decision_checkpoint_correct={signature_correct}/{total} ({signature_correct / total:.1%})")
        print(f"exact_output={exact}/{total} ({exact / total:.1%})")

    print("\nPER-SKILL CHECKPOINT ACCURACY")
    for skill in sorted(skill_total):
        hits = skill_correct[skill]
        count = skill_total[skill]
        print(f"{skill}: {hits}/{count} ({hits / count:.1%})")

    if failures:
        print("\nSAMPLE FAILURES")
        for index, (skill, stage, target, output) in enumerate(failures, start=1):
            print(f"--- {index}. {skill} stage={stage}")
            print(f"TARGET: {target}")
            print(f"MODEL:  {output}")


if __name__ == "__main__":
    main()
