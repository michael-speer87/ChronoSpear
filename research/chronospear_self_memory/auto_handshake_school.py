from __future__ import annotations

import argparse

import auto_handshake as base
from benchmark import QUESTS
from auto_handshake_resilient import (
    PLAIN_TEXT_PROTOCOL_REMINDER,
    run_one,
)


CAM_SCHOOL_CURRICULUM = r"""

CAM SCHOOL: SYNTHETIC MEMORY-NAVIGATION EXAMPLES
These examples teach how to use CAM. They are fictional and do not contain ChronoSpear benchmark answers.

GENERAL LESSONS
1. Topic-adjacent evidence is not the same as direct support. If the current evidence does not establish the claim and a useful channel still has memory, request more memory instead of filling the gap yourself.
2. Preserve evidence-state labels. HYPOTHESIS is not a decision. UNRESOLVED is not settled. EXPERIMENTALLY_PROVEN proves only what the recorded experiment actually showed.
3. Use AND for independent requests that are all valid on the current control surface. Do not use AND to create a dependent script.
4. ANSWER only when admitted evidence directly supports the answer you give. If the answer would require strengthening, guessing, or silently adding a premise, keep navigating CAM.
5. Prefer another bounded CAM request over an unsupported inference. CAM may contain a larger ecosystem than the current delta reveals.

EXAMPLE 1: RELATED EVIDENCE IS NOT ENOUGH
Question: What failure mode did the Beacon widening experiment expose?
Current admitted evidence:
- h-beacon-1 [EXPERIMENTALLY_PROVEN]: The widening probe exposed the link Rowan MEMBER_OF Lantern Guild.
Current control surface says Beacon HISTORY has more memory.
Bad response:
ANSWER: It exposed an employment-classification failure.
EVIDENCE: h-beacon-1
Why bad: MEMBER_OF does not establish employment, and h-beacon-1 does not record the failure mode.
Good response:
EXPAND Beacon HISTORY

EXAMPLE 2: DIRECT EVIDENCE IS ENOUGH
Question: What failure mode did the Beacon widening experiment expose?
Current admitted evidence:
- h-beacon-1 [EXPERIMENTALLY_PROVEN]: The widening probe exposed Rowan MEMBER_OF Lantern Guild.
- h-beacon-2 [EXPERIMENTALLY_PROVEN]: The reasoner strengthened MEMBER_OF into WORKS_FOR and answered an employment question without direct support.
Good response:
ANSWER: The experiment exposed semantic overreach: the reasoner strengthened MEMBER_OF into WORKS_FOR without direct support.
EVIDENCE: h-beacon-2

EXAMPLE 3: PRESERVE HYPOTHESIS STATE
Question: How did the archive policy change today?
Current admitted evidence:
- h-archive-1 [EXPERIMENTALLY_PROVEN]: A broad retrieval probe caused unrelated records to enter the working set.
- a-archive-1 [HYPOTHESIS]: Per-action availability maps may be a better way to bound later retrieval.
No later decision evidence is admitted.
Bad response:
ANSWER: The archive policy changed to per-action availability maps.
EVIDENCE: a-archive-1
Why bad: the evidence is a hypothesis, not a locked change.
Good response:
ANSWER: The experiment exposed overly broad retrieval, and a per-action availability map is currently a hypothesis for addressing it; the supplied evidence does not establish that the policy was changed.
EVIDENCE: h-archive-1, a-archive-1

EXAMPLE 4: USE AND FOR INDEPENDENT MEMORY NEEDS
Question: Why is a Ledger Type different from a Ledger Identity?
Current control surface:
- EXPAND Ledger Type DESCRIPTION
- EXPAND Ledger Identity DESCRIPTION
Good response:
EXPAND Ledger Type DESCRIPTION AND EXPAND Ledger Identity DESCRIPTION

EXAMPLE 5: DO NOT SCRIPT DEPENDENCIES WITH AND
Question: What happened at Glass Harbor?
Glass Harbor is not currently surfaced.
Bad response:
ACTIVATE Glass Harbor AND EXPAND Glass Harbor HISTORY
Why bad: the HISTORY request is not valid on the same pre-command surface.
Good response:
ACTIVATE Glass Harbor

EXAMPLE 6: MORE MEMORY CAN BE BETTER THAN A PLAUSIBLE GUESS
Question: Why was Project Cedar rejected?
Current admitted evidence:
- h-cedar-1 [EXPERIMENTALLY_PROVEN]: Project Cedar failed its first latency target.
Current control surface says Project Cedar HISTORY has more memory.
The first failure might be related, but it does not establish why the project was rejected.
Good response:
EXPAND Project Cedar HISTORY

End CAM SCHOOL. Apply these navigation habits to the real question while using only the real CAM evidence supplied after this curriculum.
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
            "that teaches evidence sufficiency and CAM navigation behavior."
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

    print("CHRONOSPEAR CAM SCHOOL: SYNTHETIC FEW-SHOT NAVIGATION")
    print(f"Provider: {base.provider_label()}")
    print("CAM behavior: unchanged")
    print("Memory seed/budgets: unchanged")
    print("Training intervention: synthetic navigation curriculum in the LLM system prompt")
    print("Protocol: ACTIVATE / EXPAND DESCRIPTION|ASSOCIATIONS|HISTORY / AND / ANSWER")
    print("Curriculum targets: evidence sufficiency, state-label discipline, AND, bounded recall")
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
