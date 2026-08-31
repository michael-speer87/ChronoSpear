from __future__ import annotations

import argparse

import auto_handshake as base
from benchmark import QUESTS
from auto_handshake_resilient import (
    PLAIN_TEXT_PROTOCOL_REMINDER,
    run_one,
)


CAM_SCHOOL_CURRICULUM = r"""

CAM SCHOOL V2: SYNTHETIC EVIDENCE-SUFFICIENCY AND MEMORY-NAVIGATION EXAMPLES
These examples teach how to reason with CAM. They are fictional and do not contain ChronoSpear benchmark answers.

SILENT SUFFICIENCY CHECK
Before every response, silently judge the admitted evidence against the question. Do NOT output these labels; output only the normal CAM protocol.

INSUFFICIENT: The admitted evidence cannot support the material answer yet.
PARTIAL: Some material claims are supported, but at least one important claim is still unsupported.
SUFFICIENT: Every material claim you intend to make is supported at the strength you intend to state it.

RETRIEVAL POLICY
1. If evidence is SUFFICIENT, ANSWER immediately. Memory being available is NOT a reason to retrieve it.
2. If evidence is INSUFFICIENT or PARTIAL, identify what material fact is missing, then request the smallest CAM channel likely to supply that fact.
3. Topic-adjacent evidence is not direct support. Do not strengthen a relation, invent a premise, or fill a missing fact yourself.
4. Stop retrieving as soon as the material uncertainty is resolved. Do not exhaust channels for completeness.
5. Stay with the most directly relevant surfaced concept unless admitted evidence points to another concept needed to resolve the missing fact, or the relevant channel is exhausted.
6. Preserve evidence-state labels exactly. HYPOTHESIS is not a decision. UNRESOLVED is not settled. EXPERIMENTALLY_PROVEN proves only what the experiment actually showed.
7. Use AND only for independent memory needs that are all useful now. Do not add extra commands merely because they are available.
8. CAM may contain a larger ecosystem than the current delta, but navigate that ecosystem selectively.

EXAMPLE 1: RELATED EVIDENCE MEANS KEEP LOOKING
Question: What failure mode did the Beacon widening experiment expose?
Admitted evidence:
- h-beacon-1 [EXPERIMENTALLY_PROVEN]: The widening probe exposed Rowan MEMBER_OF Lantern Guild.
Control surface: Beacon HISTORY has more memory.
Silent judgment: PARTIAL. The experiment is identified, but the failure mode is not established.
Bad response:
ANSWER: It exposed an employment-classification failure.
EVIDENCE: h-beacon-1
Good response:
EXPAND Beacon HISTORY

EXAMPLE 2: DIRECT EVIDENCE MEANS STOP, EVEN WHEN MORE MEMORY EXISTS
Question: What failure mode did the Beacon widening experiment expose?
Admitted evidence:
- h-beacon-1 [EXPERIMENTALLY_PROVEN]: The widening probe exposed Rowan MEMBER_OF Lantern Guild.
- h-beacon-2 [EXPERIMENTALLY_PROVEN]: The reasoner strengthened MEMBER_OF into WORKS_FOR and answered an employment question without direct support.
Control surface still shows more Beacon HISTORY, Beacon ASSOCIATIONS, and Lantern Guild HISTORY.
Silent judgment: SUFFICIENT. h-beacon-2 directly establishes the requested failure mode.
Bad response:
EXPAND Beacon HISTORY AND EXPAND Lantern Guild HISTORY
Why bad: available memory is not missing evidence.
Good response:
ANSWER: The experiment exposed semantic overreach: the reasoner strengthened MEMBER_OF into WORKS_FOR without direct support.
EVIDENCE: h-beacon-2

EXAMPLE 3: PARTIAL MULTI-CLAIM ANSWER
Question: What changed in Project Cedar, and why?
Admitted evidence:
- h-cedar-1 [EXPERIMENTALLY_PROVEN]: Project Cedar switched from full snapshots to deltas.
Control surface: Project Cedar HISTORY has more memory.
Silent judgment: PARTIAL. The change is supported; the reason is missing.
Good response:
EXPAND Project Cedar HISTORY

After expansion, admitted evidence also contains:
- h-cedar-2 [EXPERIMENTALLY_PROVEN]: The switch was made because repeated full snapshots dominated transfer cost.
Control surface still has more Project Cedar HISTORY.
Silent judgment: SUFFICIENT. Both requested claims are supported.
Good response:
ANSWER: Project Cedar switched from full snapshots to deltas because repeated full snapshots dominated transfer cost.
EVIDENCE: h-cedar-1, h-cedar-2

EXAMPLE 4: PRESERVE HYPOTHESIS STATE WITHOUT SEARCHING FOR A STRONGER STORY
Question: What is the current proposal for bounding archive retrieval?
Admitted evidence:
- h-archive-1 [EXPERIMENTALLY_PROVEN]: A broad retrieval probe caused unrelated records to enter the working set.
- a-archive-1 [HYPOTHESIS]: Per-action availability maps may be a better way to bound later retrieval.
Control surface has additional Archive HISTORY.
Silent judgment: SUFFICIENT for the question as asked. The proposal is known and its status is known.
Bad response:
ANSWER: The archive policy changed to per-action availability maps.
EVIDENCE: a-archive-1
Bad response:
EXPAND Archive HISTORY
Why bad: the question asks for the current proposal, not proof that the proposal became policy.
Good response:
ANSWER: The current proposal is to use per-action availability maps to bound later retrieval; it remains a hypothesis rather than an established policy change.
EVIDENCE: a-archive-1

EXAMPLE 5: SELECTIVE BRANCHING
Question: Why was the North Gate closed?
Admitted evidence:
- h-gate-1 [EXPERIMENTALLY_PROVEN]: North Gate was closed by order of Harbor Council.
- h-gate-2 [EXPERIMENTALLY_PROVEN]: The order cites structural damage reported by Bridge Office.
Control surface has North Gate HISTORY, Harbor Council HISTORY, and Bridge Office HISTORY.
Silent judgment: SUFFICIENT. The material reason is already stated.
Bad response:
EXPAND Harbor Council HISTORY AND EXPAND Bridge Office HISTORY
Good response:
ANSWER: North Gate was closed because the order cited structural damage reported by Bridge Office.
EVIDENCE: h-gate-2

If h-gate-2 had only said "see Bridge Office report for reason," then the reason would still be missing and expanding Bridge Office would be justified.

EXAMPLE 6: USE AND ONLY FOR TWO REAL MISSING FACTS
Question: Why is a Ledger Type different from a Ledger Identity?
Admitted evidence does not define either term.
Control surface:
- EXPAND Ledger Type DESCRIPTION
- EXPAND Ledger Identity DESCRIPTION
Silent judgment: INSUFFICIENT. Both definitions are independently needed for the comparison.
Good response:
EXPAND Ledger Type DESCRIPTION AND EXPAND Ledger Identity DESCRIPTION

EXAMPLE 7: DO NOT SCRIPT DEPENDENCIES WITH AND
Question: What happened at Glass Harbor?
Glass Harbor is not currently surfaced.
Bad response:
ACTIVATE Glass Harbor AND EXPAND Glass Harbor HISTORY
Why bad: the HISTORY request is not valid on the same pre-command surface.
Good response:
ACTIVATE Glass Harbor

FINAL HABIT
Ask one question before every CAM request: "What material claim can I not support yet?"
If there is no such claim, ANSWER. If there is one, request only memory likely to resolve that gap.

End CAM SCHOOL V2. Apply these habits to the real question while using only the real CAM evidence supplied after this curriculum.
"""


def install_school_prompt() -> None:
    """Install transport reminder and synthetic curriculum without changing CAM behavior."""
    prompt = base.WIRETAP_SYSTEM_PROMPT
    reminder = PLAIN_TEXT_PROTOCOL_REMINDER.strip()
    curriculum = CAM_SCHOOL_CURRICULUM.strip()
    if reminder not in prompt:
        prompt = prompt + PLAIN_TEXT_PROTOCOL_REMINDER
    if curriculum not in prompt:
        prompt = prompt + CAM_SCHOOL_CURRICULUM
    base.WIRETAP_SYSTEM_PROMPT = prompt


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the rate-limit-aware CAM handshake with a synthetic few-shot curriculum "
            "that teaches evidence sufficiency and selective CAM navigation behavior."
        )
    )
    parser.add_argument(
        "--question",
        help="Run one custom question instead of the seeded nine-case design quest.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=10,
        help="Maximum provider calls allowed per question (default: 10).",
    )
    parser.add_argument(
        "--rate-limit-retries",
        type=int,
        default=5,
        help="Maximum automatic retries for HTTP 429 per logical LLM turn (default: 5).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-round traces and print only summaries.",
    )
    args = parser.parse_args()

    install_school_prompt()

    print("CHRONOSPEAR CAM SCHOOL V2: EVIDENCE SUFFICIENCY + SELECTIVE NAVIGATION")
    print(f"Provider: {base.provider_label()}")
    print("CAM behavior: unchanged")
    print("Memory seed/budgets: unchanged")
    print("Training intervention: synthetic sufficiency/navigation curriculum in the LLM system prompt")
    print("Protocol: ACTIVATE / EXPAND DESCRIPTION|ASSOCIATIONS|HISTORY / AND / ANSWER")
    print("Curriculum targets: sufficient-vs-partial evidence, stopping, selective retrieval, state labels")
    print(f"Max rounds per question: {args.max_rounds}")
    print(f"429 retries per logical turn: {args.rate_limit_retries}")

    results: list[base.RunResult] = []
    actual_wall_total_ms = 0.0
    throttle_wait_total_ms = 0.0
    retry_total = 0

    if args.question:
        result, actual_wall_ms, throttle_wait_ms, retries = run_one(
            args.question,
            max_rounds=args.max_rounds,
            rate_limit_retries=args.rate_limit_retries,
            quiet=args.quiet,
        )
        results.append(result)
        actual_wall_total_ms += actual_wall_ms
        throttle_wait_total_ms += throttle_wait_ms
        retry_total += retries
    else:
        for case in QUESTS:
            result, actual_wall_ms, throttle_wait_ms, retries = run_one(
                case.question,
                expected_support_any=case.expected_support_any,
                max_rounds=args.max_rounds,
                rate_limit_retries=args.rate_limit_retries,
                quiet=args.quiet,
            )
            results.append(result)
            actual_wall_total_ms += actual_wall_ms
            throttle_wait_total_ms += throttle_wait_ms
            retry_total += retries

    base.print_suite_summary(results)
    print("\nCAM SCHOOL ACCOUNTING")
    print(f"curriculum_characters={len(CAM_SCHOOL_CURRICULUM)}")
    print("NOTE: provider prompt-token totals include the curriculum tax; CAM packet estimates do not.")
    print(f"429_retries={retry_total}")
    print(f"throttle_wait_total_ms={throttle_wait_total_ms:.1f}")
    print(f"actual_suite_wall_ms_including_throttle={actual_wall_total_ms:.1f}")

    none_answers = [
        result
        for result in results
        if result.status == "answered" and not result.evidence_ids
    ]
    if none_answers:
        print(
            f"grading_note: {len(none_answers)} answered case(s) used EVIDENCE:none. "
            "ID-based expected_support_hit still requires human review for synopsis/description-supported answers."
        )


if __name__ == "__main__":
    main()
