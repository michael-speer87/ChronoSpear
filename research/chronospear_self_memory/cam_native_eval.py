from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from cam_native_provider import LocalCamNativeProvider
from cam_protocol import parse_protocol_response


def _normalized(text: str) -> str:
    return "\n".join(line.strip() for line in text.strip().splitlines() if line.strip())


def _decision_signature(text: str) -> tuple[str, tuple[str, ...]]:
    decision = parse_protocol_response(text)
    if decision.kind == "activate":
        return ("activate", (decision.concept or "",))
    if decision.kind == "expand":
        return ("expand", (decision.concept or "", decision.channel or ""))
    if decision.kind == "batch":
        parts: list[str] = []
        for operation in decision.operations:
            parts.extend([operation.kind, operation.concept or "", operation.channel or ""])
        return ("batch", tuple(parts))
    if decision.kind == "answer":
        return ("answer", tuple(decision.evidence_ids))
    return (decision.kind, ())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate base or CAM-native adapter on held-out synthetic policy cases.")
    parser.add_argument("--eval", default="cam_native_data/eval.jsonl")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b")
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--show-failures", type=int, default=8)
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.eval).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit is not None:
        rows = rows[: args.limit]

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
    failures: list[tuple[str, str, str]] = []

    for row in rows:
        skill = row["skill"]
        messages = row["messages"]
        prompt_messages = messages[:-1]
        target = messages[-1]["content"]
        result = provider(prompt_messages)
        output = result.text

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
                failures.append((skill, target, output))
        except ValueError:
            if len(failures) < args.show_failures:
                failures.append((skill, target, output))

    print("CAM-NATIVE HELD-OUT POLICY EVAL")
    print(f"model={args.model}")
    print(f"adapter={'none/base-only' if args.base_only else args.adapter}")
    print(f"examples={total}")
    if total:
        print(f"protocol_valid={protocol_valid}/{total} ({protocol_valid / total:.1%})")
        print(f"decision_signature_correct={signature_correct}/{total} ({signature_correct / total:.1%})")
        print(f"exact_output={exact}/{total} ({exact / total:.1%})")

    print("\nPER-SKILL DECISION ACCURACY")
    for skill in sorted(skill_total):
        hits = skill_correct[skill]
        count = skill_total[skill]
        print(f"{skill}: {hits}/{count} ({hits / count:.1%})")

    if failures:
        print("\nSAMPLE FAILURES")
        for index, (skill, target, output) in enumerate(failures, start=1):
            print(f"--- {index}. {skill}")
            print(f"TARGET: {target}")
            print(f"MODEL:  {output}")


if __name__ == "__main__":
    main()
