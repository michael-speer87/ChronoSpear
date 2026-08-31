from __future__ import annotations

import argparse

import auto_handshake as base
from benchmark import QUESTS
from cam_native_dataset import CAM_NATIVE_SYSTEM_PROMPT
from cam_native_provider import LocalCamNativeProvider


_ORIGINAL_EXECUTE_MEMORY_ACTION = base.execute_memory_action


def _rejection_packet(memory, session, reason: str):
    """Return deterministic CAM state feedback without ending the reasoning session."""
    return base.MemoryPacket(
        question=(
            f"CAM REQUEST REJECTED: {reason}. "
            "No new memory was supplied. Choose only a command currently listed on the control surface, or ANSWER."
        ),
        new_synopses=(),
        full_descriptions=(),
        associations=(),
        history=(),
        memory_map=base._current_memory_map(memory, session),
    )


def _strict_execute_memory_action(memory, session, decision):
    """Enforce the rendered control surface for standalone EXPAND commands too.

    A stale standalone request is not a fatal CAM error. CAM reports the
    deterministic channel state back to the reasoner and leaves the session alive.
    """
    if decision.kind == "expand":
        assert decision.concept is not None
        assert decision.channel is not None
        canonical = memory._resolve_name(decision.concept)
        if canonical not in session.surfaced_concepts:
            return _rejection_packet(
                memory,
                session,
                f"{canonical} is not currently surfaced",
            )

        state = base._expand_request_state(memory, session, canonical, decision.channel)
        if state == "already_supplied":
            return _rejection_packet(
                memory,
                session,
                f"EXPAND {canonical} {decision.channel} has already been fully supplied",
            )
        if state == "invalid":
            return _rejection_packet(
                memory,
                session,
                f"EXPAND {canonical} {decision.channel} is unavailable on the current control surface",
            )

    return _ORIGINAL_EXECUTE_MEMORY_ACTION(memory, session, decision)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real ChronoSpear CAM handshake with a local base or CAM-native LoRA model.")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b")
    parser.add_argument("--base-only", action="store_true", help="Use the untrained base model as a control.")
    parser.add_argument("--question")
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    # Deliberately remove CAM School. The trained model receives only the compact native contract.
    base.WIRETAP_SYSTEM_PROMPT = CAM_NATIVE_SYSTEM_PROMPT

    # The CAM-native experiment enforces standalone channel state while keeping
    # stale requests recoverable. CAM reports deterministic state; the LLM still
    # chooses what memory to request next.
    base.execute_memory_action = _strict_execute_memory_action

    provider = LocalCamNativeProvider(
        model_name=args.model,
        adapter_path=None if args.base_only else args.adapter,
    )

    print("CHRONOSPEAR CAM-NATIVE LOCAL HANDSHAKE")
    print(f"model={args.model}")
    print(f"adapter={'none/base-only' if args.base_only else args.adapter}")
    print(f"system_prompt_characters={len(CAM_NATIVE_SYSTEM_PROMPT)}")
    print("CAM behavior=state-aware stale-request feedback")
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
