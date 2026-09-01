from __future__ import annotations

import argparse

import auto_handshake as base
from benchmark import QUESTS
from cam_native_dataset import CAM_NATIVE_SYSTEM_PROMPT
from cam_native_provider import LocalCamNativeProvider
from memory import PacketBudget


_ORIGINAL_EXECUTE_MEMORY_ACTION = base.execute_memory_action
RICH_INITIAL_BUDGET = PacketBudget(
    associations_per_concept=3,
    history_per_concept=5,
)
CAM_LITERACY_APPENDIX = """CAM MEMORY SEMANTICS

SYNOPSIS
A compact orientation to an identity. It helps establish what is nearby in memory,
but may summarize or point toward more direct memory.

DESCRIPTION
Stable clarification of what an identity is.
It directly supports definitional and identity-meaning claims.
It does not establish that an event happened.
Descriptions currently have no evidence ID, so description-only answers may use EVIDENCE: none.

ASSOCIATION
An addressable semantic assertion connecting identities.
It can directly support claims about the relationship it asserts.

HISTORICAL OCCURRENCE
An addressable immutable record of what happened.
It directly supports claims about events, changes, discoveries, experiments, and outcomes.

EVIDENCE SELECTION
Cite the supplied memory object that most directly supports the material claim.
Do not prefer a nearby or related memory merely because it led to the direct evidence.
When several memories support a claim, prefer the strongest direct support."""


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


def _rich_build_initial_packet(
    self,
    question: str,
    session: base.MemorySession,
    budget: PacketBudget = RICH_INITIAL_BUDGET,
) -> base.MemoryPacket:
    """Give explicitly activated starting concepts a richer opening workspace.

    Each explicitly activated starting concept gets its full Description plus up to
    three Associations and five History occurrences. Concepts surfaced by that
    evidence receive their normal synopsis only, so the opening packet does not
    recursively fan out.
    """
    activated = self.activate(question)
    if not activated:
        raise ValueError("No explicit ChronoSpear concept was activated by the question")
    session.surfaced_concepts.update(activated)
    return self._packet(
        question,
        activated,
        session,
        budget,
        include_description=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real ChronoSpear CAM handshake with a local base or CAM-native LoRA model.")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b")
    parser.add_argument("--base-only", action="store_true", help="Use the untrained base model as a control.")
    parser.add_argument("--question")
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--rich-initial",
        action="store_true",
        help="Give starting concepts their full Description plus up to 3 Associations and 5 History occurrences in Packet #1.",
    )
    parser.add_argument(
        "--cam-literacy",
        action="store_true",
        help="Append compact CAM memory semantics to the handshake system prompt.",
    )
    args = parser.parse_args()

    # Deliberately remove CAM School. The trained model receives only the compact native contract.
    effective_system_prompt = CAM_NATIVE_SYSTEM_PROMPT
    if args.cam_literacy:
        effective_system_prompt += "\n\n" + CAM_LITERACY_APPENDIX
    base.WIRETAP_SYSTEM_PROMPT = effective_system_prompt

    # The CAM-native experiment enforces standalone channel state while keeping
    # stale requests recoverable. CAM reports deterministic state; the LLM still
    # chooses what memory to request next.
    base.execute_memory_action = _strict_execute_memory_action

    if args.rich_initial:
        base.INITIAL_BUDGET = RICH_INITIAL_BUDGET
        base.DesignMemory.build_initial_packet = _rich_build_initial_packet

    provider = LocalCamNativeProvider(
        model_name=args.model,
        adapter_path=None if args.base_only else args.adapter,
    )

    print("CHRONOSPEAR CAM-NATIVE LOCAL HANDSHAKE")
    print(f"model={args.model}")
    print(f"adapter={'none/base-only' if args.base_only else args.adapter}")
    print(f"CAM literacy={'enabled' if args.cam_literacy else 'disabled'}")
    print(f"system_prompt_characters={len(effective_system_prompt)}")
    print("CAM behavior=state-aware stale-request feedback")
    if args.rich_initial:
        print("initial packet=full starting descriptions + up to 3 associations + up to 5 history each")
        print("later expansion behavior=unchanged")
    else:
        print("initial packet=sparse V1 baseline")
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
