"""Ask Mini-Igor questions against an imported production CAM world."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from cam_native_dataset import CAM_NATIVE_SYSTEM_PROMPT
from cam_native_provider import LocalCamNativeProvider, ProviderResult
from cam_protocol import ProtocolDecision, parse_protocol_response, render_protocol_packet
from live_quest import call_groq_model
from llama_cpp_provider import LlamaCppCamNativeProvider
from production_cam_adapter import (
    ProductionCamAdapter,
    ProductionMemoryPacket,
    ProductionMemorySession,
)

from chronospear.world_import import import_world

ProviderFn = Callable[[list[dict[str, str]]], ProviderResult]


class GroqCamNativeProvider:
    """Run the unchanged CAM-native conversation through a Groq chat model."""

    def __init__(self, model: str) -> None:
        self._model = model

    def __call__(self, messages: list[dict[str, str]]) -> ProviderResult:
        response = call_groq_model(messages, self._model)
        return ProviderResult(response.text, response.usage)


@dataclass(frozen=True)
class TranscriptMessage:
    sender: str
    content: str


@dataclass
class WorldQuestionResult:
    question: str
    world: str
    status: str = "running"
    answer: str | None = None
    evidence_ids: tuple[str, ...] = ()
    transcript: list[TranscriptMessage] = field(default_factory=list)
    admitted_evidence: dict[str, str] = field(default_factory=dict)
    admitted_descriptions: list[str] = field(default_factory=list)
    llm_calls: int = 0
    cam_expansions: int = 0
    cam_activation_count: int = 0
    cam_estimated_tokens: int = 0
    provider_prompt_tokens: int = 0
    provider_completion_tokens: int = 0
    provider_total_tokens: int = 0
    cam_time_ms: float = 0.0
    provider_time_ms: float = 0.0
    wall_time_ms: float = 0.0
    error: str | None = None


def _packet_has_payload(packet: ProductionMemoryPacket) -> bool:
    return bool(
        packet.new_synopses
        or packet.full_descriptions
        or packet.associations
        or packet.history
    )


def _record_admitted(
    result: WorldQuestionResult, packet: ProductionMemoryPacket
) -> None:
    for concept in packet.full_descriptions:
        rendered = f"{concept.name}: {concept.description}"
        if rendered not in result.admitted_descriptions:
            result.admitted_descriptions.append(rendered)
    for association in packet.associations:
        result.admitted_evidence[association.identifier] = association.render()
    for occurrence in packet.history:
        result.admitted_evidence[occurrence.identifier] = occurrence.render()


def _merge_packets(
    packets: list[ProductionMemoryPacket],
    adapter: ProductionCamAdapter,
    session: ProductionMemorySession,
) -> ProductionMemoryPacket:
    if not packets:
        return adapter.feedback(session, "AND batch supplied no new memory")
    return ProductionMemoryPacket(
        question="AND BATCH",
        new_synopses=tuple(item for packet in packets for item in packet.new_synopses),
        full_descriptions=tuple(
            item for packet in packets for item in packet.full_descriptions
        ),
        associations=tuple(item for packet in packets for item in packet.associations),
        history=tuple(item for packet in packets for item in packet.history),
        memory_map=packets[-1].memory_map,
    )


def _execute_decision(
    adapter: ProductionCamAdapter,
    session: ProductionMemorySession,
    decision: ProtocolDecision,
) -> tuple[ProductionMemoryPacket, int, int]:
    operations = decision.operations if decision.kind == "batch" else (decision,)
    if not operations:
        return adapter.feedback(session, "AND batch is empty"), 0, 0

    surfaced_before = set(session.surfaced_concepts)
    resolved: list[tuple[ProtocolDecision, str]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for operation in operations:
        if operation.kind == "activate":
            assert operation.concept is not None
            try:
                canonical = adapter.resolve_name(operation.concept)
            except KeyError:
                return adapter.feedback(
                    session, f"ACTIVATE {operation.concept} is unavailable"
                ), 0, 0
            if canonical in surfaced_before:
                return adapter.feedback(
                    session, f"ACTIVATE {canonical} is already surfaced"
                ), 0, 0
            key = ("activate", canonical, None)
        elif operation.kind == "expand":
            assert operation.concept is not None
            assert operation.channel is not None
            try:
                canonical = adapter.resolve_name(operation.concept)
            except KeyError:
                return adapter.feedback(
                    session, f"EXPAND {operation.concept} is unavailable"
                ), 0, 0
            if canonical not in surfaced_before:
                return adapter.feedback(
                    session, f"EXPAND {canonical} requires a surfaced Identity"
                ), 0, 0
            state = adapter.expansion_state(
                canonical, operation.channel, session
            )
            if state != "available":
                return adapter.feedback(
                    session,
                    f"EXPAND {canonical} {operation.channel} is "
                    f"{state.replace('_', ' ')}",
                ), 0, 0
            key = ("expand", canonical, operation.channel)
        else:
            return adapter.feedback(
                session, "AND accepts only ACTIVATE and EXPAND"
            ), 0, 0
        if key in seen:
            return adapter.feedback(session, f"duplicate AND operation: {key}"), 0, 0
        seen.add(key)
        resolved.append((operation, canonical))

    packets: list[ProductionMemoryPacket] = []
    activations = 0
    expansions = 0
    for operation, canonical in resolved:
        if operation.kind == "activate":
            packets.append(adapter.activate(canonical, session))
            activations += 1
        else:
            assert operation.channel is not None
            packets.append(adapter.expand(canonical, operation.channel, session))
            expansions += 1
    return _merge_packets(packets, adapter, session), activations, expansions


def _usage_int(usage: dict[str, object], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def run_world_question(
    world_path: str | Path,
    question: str,
    *,
    provider_fn: ProviderFn,
    max_rounds: int = 10,
    system_prompt: str = CAM_NATIVE_SYSTEM_PROMPT,
) -> WorldQuestionResult:
    """Run one production-CAM conversation and retain exact external messages."""

    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    total_start = perf_counter()
    path = Path(world_path)
    result = WorldQuestionResult(question=question, world=str(path))
    memory_bytes = (path / "memory.json").read_bytes()

    cam_start = perf_counter()
    try:
        adapter = ProductionCamAdapter(import_world(path))
        session = ProductionMemorySession()
        packet = adapter.build_initial_packet(question, session)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result.status = "cam_initial_failure"
        result.error = str(exc)
        result.cam_time_ms = (perf_counter() - cam_start) * 1000
        result.wall_time_ms = (perf_counter() - total_start) * 1000
        if (path / "memory.json").read_bytes() != memory_bytes:
            raise RuntimeError("Question harness modified memory.json") from exc
        return result
    result.cam_time_ms += (perf_counter() - cam_start) * 1000
    result.cam_activation_count = len(adapter.activate_question(question))
    messages = [{"role": "system", "content": system_prompt}]

    for _round in range(1, max_rounds + 1):
        _record_admitted(result, packet)
        rendered = render_protocol_packet(packet)
        result.transcript.append(TranscriptMessage("CAM", rendered))
        result.cam_estimated_tokens += packet.estimated_tokens
        messages.append({"role": "user", "content": rendered})

        provider_start = perf_counter()
        try:
            provider_result = provider_fn(messages)
        except RuntimeError as exc:
            result.status = "provider_failure"
            result.error = str(exc)
            break
        result.provider_time_ms += (perf_counter() - provider_start) * 1000
        result.llm_calls += 1
        result.provider_prompt_tokens += _usage_int(
            provider_result.usage, "prompt_tokens"
        )
        result.provider_completion_tokens += _usage_int(
            provider_result.usage, "completion_tokens"
        )
        result.provider_total_tokens += _usage_int(
            provider_result.usage, "total_tokens"
        )
        raw_response = provider_result.text
        result.transcript.append(TranscriptMessage("MINI-IGOR", raw_response))
        messages.append({"role": "assistant", "content": raw_response})

        try:
            decision = parse_protocol_response(raw_response)
        except ValueError as exc:
            result.status = "protocol_failure"
            result.error = str(exc)
            break
        if decision.kind == "answer":
            unadmitted_ids = tuple(
                identifier
                for identifier in decision.evidence_ids
                if identifier.casefold() != "none"
                and identifier not in result.admitted_evidence
            )
            if unadmitted_ids:
                result.status = "evidence_failure"
                result.error = (
                    "ANSWER cited evidence not admitted in this session: "
                    + ", ".join(unadmitted_ids)
                )
                break
            result.status = "answered"
            result.answer = decision.answer
            result.evidence_ids = decision.evidence_ids
            break

        cam_start = perf_counter()
        packet, activations, expansions = _execute_decision(
            adapter, session, decision
        )
        result.cam_time_ms += (perf_counter() - cam_start) * 1000
        result.cam_activation_count += activations
        result.cam_expansions += expansions
    else:
        result.status = "max_rounds"
        result.error = f"No final ANSWER within {max_rounds} rounds"

    if (path / "memory.json").read_bytes() != memory_bytes:
        raise RuntimeError("Question harness modified memory.json")
    result.wall_time_ms = (perf_counter() - total_start) * 1000
    return result


def print_transcript(result: WorldQuestionResult) -> None:
    line = "=" * 60
    divider = "-" * 60
    print(line)
    print("MINI-IGOR <-> CAM TRANSCRIPT")
    print(f"Question: {result.question}")
    print(f"World: {result.world}")
    print(line)
    for message in result.transcript:
        print(f"\n{message.sender} -> {'MINI-IGOR' if message.sender == 'CAM' else 'CAM'}\n")
        print(message.content)
        print(f"\n{divider}")
    print("\nMINI-IGOR FINAL ANSWER\n")
    print(result.answer or f"No answer ({result.error or result.status})")
    print(f"\n{line}")
    print(f"status={result.status}")
    print(f"LLM calls={result.llm_calls}")
    print(f"CAM expansions={result.cam_expansions}")
    print(f"CAM activation count={result.cam_activation_count}")
    print(f"CAM estimated tokens={result.cam_estimated_tokens}")
    print(f"provider prompt tokens={result.provider_prompt_tokens}")
    print(f"provider completion tokens={result.provider_completion_tokens}")
    print(f"total provider tokens={result.provider_total_tokens}")
    print(f"CAM time={result.cam_time_ms:.3f} ms")
    print(f"provider time={result.provider_time_ms:.3f} ms")
    print(f"wall time={result.wall_time_ms:.3f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask Mini-Igor one question against an imported production CAM world."
    )
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--provider",
        choices=("transformers", "llama-cpp", "groq"),
        default="transformers",
    )
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--adapter", default="cam_native_adapter_qwen3_0_6b")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--llama-model", default="cam-native-v1")
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--show-system", action="store_true")
    args = parser.parse_args()

    provider: ProviderFn
    if args.provider == "groq":
        provider = GroqCamNativeProvider(args.model)
    elif args.provider == "llama-cpp":
        provider = LlamaCppCamNativeProvider(
            base_url=args.llama_url, model=args.llama_model
        )
    else:
        provider = LocalCamNativeProvider(
            model_name=args.model, adapter_path=args.adapter
        )
    if args.show_system:
        print("MINI-IGOR SYSTEM CONTRACT\n")
        print(CAM_NATIVE_SYSTEM_PROMPT)
        print()
    result = run_world_question(
        args.world,
        args.question,
        provider_fn=provider,
        max_rounds=args.max_rounds,
    )
    print_transcript(result)


if __name__ == "__main__":
    main()
