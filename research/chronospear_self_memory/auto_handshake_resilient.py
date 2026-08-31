from __future__ import annotations

import argparse
from dataclasses import replace
import re
from time import sleep

import auto_handshake as base
from benchmark import QUESTS


PLAIN_TEXT_PROTOCOL_REMINDER = """

IMPORTANT TRANSPORT RULE:
CAM commands are plain-text response lines, not function calls or tool calls.
Never emit a tool/function invocation. Return the command itself as ordinary assistant text.
"""


class RateLimitAwareProvider:
    """Retry only Groq 429 throttles while preserving other provider failures."""

    def __init__(self, *, max_retries: int = 5, quiet: bool = False) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.max_retries = max_retries
        self.quiet = quiet
        self.call_wait_ms: list[float] = []
        self.total_wait_ms = 0.0
        self.retry_count = 0

    @staticmethod
    def _retry_after_seconds(message: str) -> float | None:
        if "429" not in message and "rate limit" not in message.casefold():
            return None
        match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", message, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return 6.0

    def __call__(self, messages: list[dict[str, str]]):
        wait_this_call_ms = 0.0
        attempts = 0
        while True:
            try:
                result = base.call_provider(messages)
            except RuntimeError as exc:
                retry_after = self._retry_after_seconds(str(exc))
                if retry_after is None or attempts >= self.max_retries:
                    self.call_wait_ms.append(wait_this_call_ms)
                    raise

                attempts += 1
                self.retry_count += 1
                # Small cushion so a retry does not land exactly on the provider's boundary.
                wait_seconds = retry_after + 0.25
                wait_ms = wait_seconds * 1000.0
                wait_this_call_ms += wait_ms
                self.total_wait_ms += wait_ms
                if not self.quiet:
                    print(
                        f"RATE LIMIT: waiting {wait_seconds:.3f}s before retry "
                        f"({attempts}/{self.max_retries}); wait is tracked separately from active latency."
                    )
                sleep(wait_seconds)
                continue

            self.call_wait_ms.append(wait_this_call_ms)
            return result


def remove_throttle_wait_from_metrics(
    result: base.RunResult,
    provider: RateLimitAwareProvider,
) -> tuple[float, float]:
    """Keep active interaction latency separate from provider throttle sleep."""
    actual_wall_ms = result.total_elapsed_ms

    adjusted_rounds: list[base.RoundMetric] = []
    successful_wait_ms = 0.0
    for index, metric in enumerate(result.rounds):
        wait_ms = provider.call_wait_ms[index] if index < len(provider.call_wait_ms) else 0.0
        successful_wait_ms += wait_ms
        adjusted_rounds.append(
            replace(metric, provider_ms=max(0.0, metric.provider_ms - wait_ms))
        )
    result.rounds = adjusted_rounds

    # run_question records provider_ms only for calls that returned successfully.
    result.total_provider_ms = max(0.0, result.total_provider_ms - successful_wait_ms)
    result.total_elapsed_ms = max(0.0, result.total_elapsed_ms - provider.total_wait_ms)
    return actual_wall_ms, provider.total_wait_ms


def run_one(
    question: str,
    *,
    expected_support_any: frozenset[str] = frozenset(),
    max_rounds: int,
    rate_limit_retries: int,
    quiet: bool,
) -> tuple[base.RunResult, float, float, int]:
    provider = RateLimitAwareProvider(max_retries=rate_limit_retries, quiet=quiet)
    result = base.run_question(
        question,
        expected_support_any=expected_support_any,
        provider_fn=provider,
        max_rounds=max_rounds,
        verbose=not quiet,
    )
    actual_wall_ms, throttle_wait_ms = remove_throttle_wait_from_metrics(result, provider)
    return result, actual_wall_ms, throttle_wait_ms, provider.retry_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the autonomous CAM <-> LLM handshake with Groq 429 retry/pacing while "
            "keeping throttle wait separate from active latency."
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

    # Tighten only the LLM-side transport instruction. CAM memory behavior is unchanged.
    base.WIRETAP_SYSTEM_PROMPT = base.WIRETAP_SYSTEM_PROMPT + PLAIN_TEXT_PROTOCOL_REMINDER

    print("CHRONOSPEAR AUTONOMOUS CAM <-> LLM HANDSHAKE: RATE-LIMIT-AWARE")
    print(f"Provider: {base.provider_label()}")
    print("Protocol: ACTIVATE / EXPAND DESCRIPTION|ASSOCIATIONS|HISTORY / AND / ANSWER")
    print("AND: up to four independent current-surface memory commands per LLM turn")
    print("Transport: CAM commands must be plain text, never tool/function calls")
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
    print("\nRATE-LIMIT / TRANSPORT ACCOUNTING")
    print(f"429_retries={retry_total}")
    print(f"throttle_wait_total_ms={throttle_wait_total_ms:.1f}")
    print(f"actual_suite_wall_ms_including_throttle={actual_wall_total_ms:.1f}")
    print(
        "NOTE: suite latency above is normalized to active work by subtracting 429 sleep time; "
        "actual wall includes provider throttling."
    )

    none_answers = [
        result
        for result in results
        if result.status == "answered" and not result.evidence_ids
    ]
    if none_answers:
        print(
            f"grading_note: {len(none_answers)} answered case(s) used EVIDENCE:none. "
            "expected_support_hit is ID-based, so these require human review when synopsis/description "
            "may itself be sufficient."
        )


if __name__ == "__main__":
    main()
