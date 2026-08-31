from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
from statistics import mean, median
from time import perf_counter
from typing import Callable

from benchmark import QUESTS, QuestCase
from cam_protocol import ProtocolDecision, parse_protocol_response
from live_quest import ProviderResult, call_provider
from memory import DesignMemory, MemoryPacket, MemorySession
from playground import INITIAL_BUDGET
from seed import build_memory
from wiretap_playground import WIRETAP_SYSTEM_PROMPT, provider_label


ProviderFn = Callable[[list[dict[str, str]]], ProviderResult]


@dataclass(frozen=True)
class RoundMetric:
    number: int
    packet_estimated_tokens: int
    provider_ms: float
    decision: ProtocolDecision | None
    raw_response: str
    usage: dict[str, object]
    parse_error: str | None = None
    cam_operation_ms: float = 0.0


@dataclass
class RunResult:
    question: str
    expected_support_any: frozenset[str]
    status: str
    answer: str | None = None
    evidence_ids: tuple[str, ...] = ()
    rounds: list[RoundMetric] = field(default_factory=list)
    commands: Counter[str] = field(default_factory=Counter)
    initial_cam_ms: float = 0.0
    total_cam_ms: float = 0.0
    total_provider_ms: float = 0.0
    total_elapsed_ms: float = 0.0
    cam_packet_estimated_tokens: int = 0
    provider_usage_totals: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    @property
    def support_hit(self) -> bool | None:
        if not self.expected_support_any:
            return None
        return bool(set(self.evidence_ids) & set(self.expected_support_any))


def packet_has_payload(packet: MemoryPacket) -> bool:
    return bool(
        packet.new_synopses
        or packet.full_descriptions
        or packet.associations
        or packet.history
    )


def add_numeric_usage(totals: dict[str, float], usage: dict[str, object]) -> None:
    for key, value in usage.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            totals[key] = totals.get(key, 0.0) + float(value)


def exact_activate(memory: DesignMemory, concept: str, session: MemorySession) -> MemoryPacket:
    """Strict exact/alias activation. No fuzzy matching and no semantic inference."""
    canonical = memory._resolve_name(concept)
    if canonical in session.surfaced_concepts:
        raise ValueError(f"Concept is already surfaced: {canonical}")

    session.surfaced_concepts.add(canonical)
    return memory._packet(
        "ACTIVATION",
        (canonical,),
        session,
        INITIAL_BUDGET,
        include_description=False,
    )


def execute_memory_action(
    memory: DesignMemory,
    session: MemorySession,
    decision: ProtocolDecision,
) -> MemoryPacket:
    if decision.kind == "activate":
        assert decision.concept is not None
        return exact_activate(memory, decision.concept, session)

    if decision.kind == "expand":
        assert decision.concept is not None
        assert decision.channel is not None
        return memory.expand_channel(
            decision.concept,
            decision.channel,
            session,
            page_size=1,
        )

    raise ValueError(f"Decision kind is not a CAM memory action: {decision.kind}")


def command_label(decision: ProtocolDecision) -> str:
    if decision.kind == "activate":
        return "ACTIVATE"
    if decision.kind == "expand":
        return f"EXPAND {decision.channel}"
    return decision.kind.upper()


def print_packet_summary(packet: MemoryPacket) -> None:
    print(
        "CAM delta: "
        f"synopses={len(packet.new_synopses)} "
        f"descriptions={len(packet.full_descriptions)} "
        f"associations={len(packet.associations)} "
        f"history={len(packet.history)} "
        f"est_tokens={packet.estimated_tokens}"
    )


def run_question(
    question: str,
    *,
    expected_support_any: frozenset[str] = frozenset(),
    provider_fn: ProviderFn = call_provider,
    max_rounds: int = 10,
    verbose: bool = True,
) -> RunResult:
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")

    result = RunResult(
        question=question,
        expected_support_any=expected_support_any,
        status="running",
    )
    total_start = perf_counter()
    memory = build_memory()
    session = MemorySession()

    cam_start = perf_counter()
    try:
        packet = memory.build_initial_packet(question, session, INITIAL_BUDGET)
    except (KeyError, ValueError) as exc:
        result.status = "cam_initial_failure"
        result.error = str(exc)
        result.total_elapsed_ms = (perf_counter() - total_start) * 1000
        return result
    result.initial_cam_ms = (perf_counter() - cam_start) * 1000
    result.total_cam_ms += result.initial_cam_ms
    result.cam_packet_estimated_tokens += packet.estimated_tokens

    messages: list[dict[str, str]] = [
        {"role": "system", "content": WIRETAP_SYSTEM_PROMPT},
    ]

    if verbose:
        print("\n" + "=" * 96)
        print(question)
        print("=" * 96)
        print(f"Initial CAM build: {result.initial_cam_ms:.3f} ms")
        print_packet_summary(packet)

    for round_number in range(1, max_rounds + 1):
        messages.append({"role": "user", "content": packet.render()})

        provider_start = perf_counter()
        try:
            provider_result = provider_fn(messages)
        except RuntimeError as exc:
            result.status = "provider_failure"
            result.error = str(exc)
            break
        provider_ms = (perf_counter() - provider_start) * 1000
        result.total_provider_ms += provider_ms
        add_numeric_usage(result.provider_usage_totals, provider_result.usage)
        messages.append({"role": "assistant", "content": provider_result.text})

        try:
            decision = parse_protocol_response(provider_result.text)
            parse_error = None
        except ValueError as exc:
            decision = None
            parse_error = str(exc)

        metric = RoundMetric(
            number=round_number,
            packet_estimated_tokens=packet.estimated_tokens,
            provider_ms=provider_ms,
            decision=decision,
            raw_response=provider_result.text,
            usage=provider_result.usage,
            parse_error=parse_error,
        )
        result.rounds.append(metric)

        if verbose:
            print(f"\nROUND {round_number} | provider={provider_ms:.1f} ms")
            print(f"LLM -> {provider_result.text.strip()}")

        if decision is None:
            result.status = "protocol_failure"
            result.error = parse_error
            if verbose:
                print(f"PROTOCOL FAILURE: {parse_error}")
            break

        if decision.kind == "answer":
            result.status = "answered"
            result.answer = decision.answer
            result.evidence_ids = decision.evidence_ids
            result.commands["ANSWER"] += 1
            break

        result.commands[command_label(decision)] += 1

        cam_start = perf_counter()
        try:
            next_packet = execute_memory_action(memory, session, decision)
        except (KeyError, ValueError) as exc:
            cam_ms = (perf_counter() - cam_start) * 1000
            result.total_cam_ms += cam_ms
            result.status = "cam_operation_failure"
            result.error = str(exc)
            result.rounds[-1] = RoundMetric(
                **{**metric.__dict__, "cam_operation_ms": cam_ms}
            )
            if verbose:
                print(f"CAM OPERATION FAILURE after {cam_ms:.3f} ms: {exc}")
            break

        cam_ms = (perf_counter() - cam_start) * 1000
        result.total_cam_ms += cam_ms
        result.rounds[-1] = RoundMetric(
            **{**metric.__dict__, "cam_operation_ms": cam_ms}
        )
        packet = next_packet
        result.cam_packet_estimated_tokens += packet.estimated_tokens

        if verbose:
            payload_note = "payload" if packet_has_payload(packet) else "empty channel result"
            print(f"CAM -> {payload_note} in {cam_ms:.3f} ms")
            print_packet_summary(packet)
    else:
        result.status = "max_rounds"
        result.error = f"No final ANSWER within {max_rounds} rounds"

    result.total_elapsed_ms = (perf_counter() - total_start) * 1000

    if verbose:
        print("\nRESULT")
        print(f"status={result.status}")
        if result.answer:
            print(f"answer={result.answer}")
            print(f"evidence={','.join(result.evidence_ids) or 'none'}")
        if result.support_hit is not None:
            print(f"expected_support_hit={result.support_hit}")
        if result.error:
            print(f"error={result.error}")
        print(
            f"wall={result.total_elapsed_ms:.1f} ms | "
            f"provider={result.total_provider_ms:.1f} ms | "
            f"CAM={result.total_cam_ms:.3f} ms | "
            f"LLM_calls={len(result.rounds)} | "
            f"CAM_packet_est_tokens={result.cam_packet_estimated_tokens}"
        )
        if result.provider_usage_totals:
            print(f"provider_usage_totals={json.dumps(result.provider_usage_totals, sort_keys=True)}")
        if result.commands:
            print(f"commands={dict(result.commands)}")

    return result


def run_case(
    case: QuestCase,
    *,
    provider_fn: ProviderFn = call_provider,
    max_rounds: int = 10,
    verbose: bool = True,
) -> RunResult:
    return run_question(
        case.question,
        expected_support_any=case.expected_support_any,
        provider_fn=provider_fn,
        max_rounds=max_rounds,
        verbose=verbose,
    )


def print_suite_summary(results: list[RunResult]) -> None:
    print("\n" + "#" * 96)
    print("AUTONOMOUS HANDSHAKE SUITE SUMMARY")
    print("#" * 96)

    answered = [result for result in results if result.status == "answered"]
    support_scored = [result for result in answered if result.support_hit is not None]
    support_hits = [result for result in support_scored if result.support_hit]
    command_totals: Counter[str] = Counter()
    for result in results:
        command_totals.update(result.commands)

    provider_latencies = [round_.provider_ms for result in results for round_ in result.rounds]
    wall_times = [result.total_elapsed_ms for result in results]
    rounds = [len(result.rounds) for result in results]

    print(f"provider={provider_label()}")
    print(f"cases={len(results)} answered={len(answered)}")
    if support_scored:
        print(f"expected_support_hits={len(support_hits)}/{len(support_scored)}")
    print(f"status_counts={dict(Counter(result.status for result in results))}")
    print(f"command_counts={dict(command_totals)}")

    if provider_latencies:
        print(
            f"LLM call latency: avg={mean(provider_latencies):.1f} ms "
            f"median={median(provider_latencies):.1f} ms "
            f"calls={len(provider_latencies)}"
        )
    if wall_times:
        print(
            f"case wall time: avg={mean(wall_times):.1f} ms "
            f"median={median(wall_times):.1f} ms"
        )
    if rounds:
        print(f"LLM calls per case: avg={mean(rounds):.2f} median={median(rounds):.2f}")

    print(f"total_provider_ms={sum(result.total_provider_ms for result in results):.1f}")
    print(f"total_CAM_ms={sum(result.total_cam_ms for result in results):.3f}")
    print(f"total_CAM_packet_est_tokens={sum(result.cam_packet_estimated_tokens for result in results)}")

    usage_totals: dict[str, float] = {}
    for result in results:
        for key, value in result.provider_usage_totals.items():
            usage_totals[key] = usage_totals.get(key, 0.0) + value
    if usage_totals:
        print(f"provider_usage_totals={json.dumps(usage_totals, sort_keys=True)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the CAM <-> LLM control-vocabulary handshake without human intervention."
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
        "--quiet",
        action="store_true",
        help="Suppress per-round traces and print only the suite summary.",
    )
    args = parser.parse_args()

    print("CHRONOSPEAR AUTONOMOUS CAM <-> LLM HANDSHAKE")
    print(f"Provider: {provider_label()}")
    print("Protocol: ACTIVATE / EXPAND DESCRIPTION|ASSOCIATIONS|HISTORY / ANSWER")
    print(f"Max rounds per question: {args.max_rounds}")

    if args.question:
        result = run_question(
            args.question,
            max_rounds=args.max_rounds,
            verbose=not args.quiet,
        )
        print_suite_summary([result])
        return

    results = [
        run_case(case, max_rounds=args.max_rounds, verbose=not args.quiet)
        for case in QUESTS
    ]
    print_suite_summary(results)


if __name__ == "__main__":
    main()
