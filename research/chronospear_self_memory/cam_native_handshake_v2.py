from __future__ import annotations

import argparse

import auto_handshake as base
from benchmark import QUESTS
from cam_native_dataset_v2 import CAM_NATIVE_SYSTEM_PROMPT_V2
from cam_native_handshake import _strict_execute_memory_action
from cam_native_provider import LocalCamNativeProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real ChronoSpear CAM handshake with the CAM-native V2 adapter.")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b_v2")
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--question")
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    base.WIRETAP_SYSTEM_PROMPT = CAM_NATIVE_SYSTEM_PROMPT_V2
    base.execute_memory_action = _strict_execute_memory_action

    provider = LocalCamNativeProvider(
        model_name=args.model,
        adapter_path=None if args.base_only else args.adapter,
    )

    print("CHRONOSPEAR CAM-NATIVE V2 LOCAL HANDSHAKE")
    print(f"model={args.model}")
    print(f"adapter={'none/base-only' if args.base_only else args.adapter}")
    print(f"system_prompt_characters={len(CAM_NATIVE_SYSTEM_PROMPT_V2)}")
    print("CAM behavior=state-aware stale-request feedback")
    print("training behavior=multi-round V2")
    print("CAM School=disabled")
    print(f"max_rounds={args.max_rounds}")

    if args.question:
        result = base.run_question(
            args.question,
            provider_fn=provider,
            max_rounds=args.max_rounds,
            verbose=not args.quiet,
        )
        base.print_suite_summary([result])
        return

    results = [
        base.run_case(
            case,
            provider_fn=provider,
            max_rounds=args.max_rounds,
            verbose=not args.quiet,
        )
        for case in QUESTS
    ]
    base.print_suite_summary(results)


if __name__ == "__main__":
    main()
