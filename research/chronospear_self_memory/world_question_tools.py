"""Tool-driven question harness over the read-only production CAM adapter."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Protocol

from llama_cpp_provider import LlamaCppToolProvider
from production_cam_adapter import (
    ProductionCamAdapter,
    ProductionMemoryPacket,
    ProductionMemorySession,
)
from world_writer import (
    GroqWriterProvider,
    WriterProviderResult,
)

from chronospear.world_import import import_world

SYSTEM_PROMPT = """You answer questions using only supplied world memory.
If supplied evidence does not directly support a requested factual claim, use the
available memory tools to retrieve what you need. Do not guess historical facts
from related records. Use submit_answer only after you have sufficient evidence.
Only cite evidence IDs actually returned to you. If retrieval is exhausted, submit
an answer explicitly stating insufficient evidence with an empty evidence_ids list."""


def _function(
    name: str,
    description: str,
    properties: dict[str, object],
    required: list[str],
) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_NAME = {"name": {"type": "string", "description": "Exact identity name or alias."}}
CAM_TOOLS: tuple[dict[str, object], ...] = (
    _function(
        "get_history",
        "Return the next bounded History delta for a surfaced identity.",
        _NAME,
        ["name"],
    ),
    _function(
        "get_associations",
        "Return the next bounded Association delta for a surfaced identity.",
        _NAME,
        ["name"],
    ),
    _function(
        "get_description",
        "Return an available Description for a surfaced identity.",
        _NAME,
        ["name"],
    ),
    _function("activate", "Activate an exact unsurfaced identity or alias.", _NAME, ["name"]),
    _function(
        "submit_answer",
        "Submit the final answer and exact admitted evidence IDs.",
        {
            "answer": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
        ["answer", "evidence_ids"],
    ),
)


class ToolCall(Protocol):
    call_id: str
    name: str
    arguments: str


class ToolResponse(Protocol):
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    usage: dict[str, object]


class ToolProvider(Protocol):
    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> ToolResponse: ...


class GroqCamToolProvider:
    def __init__(self, model: str, tool_choice: str = "auto") -> None:
        self._transport = GroqWriterProvider(model, tool_choice)

    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> WriterProviderResult:
        return self._transport(messages, tools)


@dataclass(frozen=True)
class TranscriptMessage:
    sender: str
    recipient: str
    content: str


@dataclass
class ToolQuestionResult:
    question: str
    world: str
    status: str = "running"
    answer: str | None = None
    evidence_ids: tuple[str, ...] = ()
    admitted_evidence: dict[str, str] = field(default_factory=dict)
    admitted_descriptions: list[str] = field(default_factory=list)
    transcript: list[TranscriptMessage] = field(default_factory=list)
    llm_calls: int = 0
    cam_tool_calls: int = 0
    history_calls: int = 0
    association_calls: int = 0
    description_calls: int = 0
    activations: int = 0
    cam_estimated_tokens: int = 0
    provider_prompt_tokens: int = 0
    provider_completion_tokens: int = 0
    provider_total_tokens: int = 0
    provider_retries: int = 0
    provider_time_ms: float = 0.0
    cam_time_ms: float = 0.0
    wall_time_ms: float = 0.0
    error: str | None = None
    structured_tool_calls_present: bool | None = None


def _usage(usage: dict[str, object], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _admit(result: ToolQuestionResult, packet: ProductionMemoryPacket) -> None:
    for concept in packet.full_descriptions:
        rendered = f"{concept.name}: {concept.description}"
        if rendered not in result.admitted_descriptions:
            result.admitted_descriptions.append(rendered)
    for item in packet.associations:
        result.admitted_evidence[item.identifier] = item.render()
    for item in packet.history:
        result.admitted_evidence[item.identifier] = item.render()


def _arguments(call: ToolCall) -> dict[str, object]:
    try:
        value = json.loads(call.arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("tool arguments must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be an object")
    return value


def _name_argument(arguments: dict[str, object]) -> str:
    if set(arguments) != {"name"} or not isinstance(arguments["name"], str):
        raise ValueError("CAM retrieval tools require exactly one string name")
    if not arguments["name"].strip():
        raise ValueError("CAM retrieval tool name cannot be blank")
    return arguments["name"]


def _tool_result_message(call: ToolCall, content: str) -> dict[str, object]:
    return {
        "role": "tool",
        "tool_call_id": call.call_id,
        "name": call.name,
        "content": content,
    }


def _assistant_call_message(call: ToolCall) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": call.call_id,
            "type": "function",
            "function": {"name": call.name, "arguments": call.arguments},
        }],
    }


def _sanitized_assistant_message(response: ToolResponse) -> dict[str, object]:
    raw = getattr(response, "raw_assistant_message", None)
    if isinstance(raw, dict):
        sanitized: dict[str, object] = {"content": raw.get("content")}
        if "tool_calls" in raw:
            sanitized["tool_calls"] = raw["tool_calls"]
        return sanitized
    return {
        "content": response.content,
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in response.tool_calls
        ],
    }


def run_world_question_tools(
    world_path: str | Path,
    question: str,
    *,
    provider_fn: ToolProvider,
    max_rounds: int = 10,
) -> ToolQuestionResult:
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    started = perf_counter()
    path = Path(world_path)
    memory_path = path / "memory.json"
    memory_bytes = memory_path.read_bytes()
    result = ToolQuestionResult(question, str(path))
    cam_started = perf_counter()
    try:
        adapter = ProductionCamAdapter(import_world(path))
        session = ProductionMemorySession()
        opening = adapter.build_initial_packet(question, session)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result.status = "cam_initial_failure"
        result.error = str(exc)
        result.wall_time_ms = (perf_counter() - started) * 1000
        return result
    result.cam_time_ms += (perf_counter() - cam_started) * 1000
    result.activations = len(adapter.activate_question(question))
    result.cam_estimated_tokens += opening.estimated_tokens
    _admit(result, opening)
    opening_text = opening.render()
    result.transcript.append(TranscriptMessage("CAM", "LIBRARIAN", opening_text))
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": opening_text},
    ]

    for _round in range(max_rounds):
        provider_started = perf_counter()
        try:
            response = provider_fn(messages, CAM_TOOLS)
        except RuntimeError as exc:
            result.status = "provider_failure"
            result.error = str(exc)
            break
        result.provider_time_ms += (perf_counter() - provider_started) * 1000
        result.llm_calls += 1
        result.provider_prompt_tokens += _usage(response.usage, "prompt_tokens")
        result.provider_completion_tokens += _usage(response.usage, "completion_tokens")
        result.provider_total_tokens += _usage(response.usage, "total_tokens")
        result.provider_retries += _usage(response.usage, "provider_retries")
        if len(response.tool_calls) != 1 or (response.content or "").strip():
            present = getattr(response, "tool_calls_present", None)
            result.structured_tool_calls_present = (
                present if isinstance(present, bool) else bool(response.tool_calls)
            )
            raw_message = json.dumps(
                _sanitized_assistant_message(response),
                ensure_ascii=False,
                indent=2,
            )
            result.transcript.append(
                TranscriptMessage("LIBRARIAN", "HARNESS", raw_message)
            )
            result.status = "tool_protocol_failure"
            result.error = "Librarian must make exactly one tool call per round"
            break
        call = response.tool_calls[0]
        result.cam_tool_calls += 1
        messages.append(_assistant_call_message(call))
        try:
            arguments = _arguments(call)
            if call.name == "submit_answer":
                if set(arguments) != {"answer", "evidence_ids"}:
                    raise ValueError("submit_answer requires answer and evidence_ids")
                answer = arguments["answer"]
                ids = arguments["evidence_ids"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("submit_answer answer must be non-empty")
                if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                    raise ValueError("submit_answer evidence_ids must be a string list")
                unadmitted = [item for item in ids if item not in result.admitted_evidence]
                if unadmitted:
                    raise ValueError("unadmitted evidence IDs: " + ", ".join(unadmitted))
                result.transcript.append(
                    TranscriptMessage("LIBRARIAN", "ANSWER TOOL", call.arguments)
                )
                result.status = "answered"
                result.answer = answer
                result.evidence_ids = tuple(ids)
                break

            name = _name_argument(arguments)
            result.transcript.append(
                TranscriptMessage(
                    "LIBRARIAN", "CAM TOOL", f"{call.name}(name={name!r})"
                )
            )
            cam_started = perf_counter()
            if call.name == "activate":
                canonical = adapter.resolve_name(name)
                if canonical in session.surfaced_concepts:
                    raise ValueError(f"activate identity is already surfaced: {canonical}")
                packet = adapter.activate(canonical, session)
                result.activations += 1
            else:
                channels = {
                    "get_history": "HISTORY",
                    "get_associations": "ASSOCIATIONS",
                    "get_description": "DESCRIPTION",
                }
                if call.name not in channels:
                    raise ValueError(f"unknown tool: {call.name}")
                canonical = adapter.resolve_name(name)
                if canonical not in session.surfaced_concepts:
                    raise ValueError(f"identity is not surfaced: {canonical}")
                channel = channels[call.name]
                if adapter.expansion_state(canonical, channel, session) != "available":
                    raise ValueError(f"{call.name} is unavailable for {canonical}")
                packet = adapter.expand(canonical, channel, session)
                if call.name == "get_history":
                    result.history_calls += 1
                elif call.name == "get_associations":
                    result.association_calls += 1
                else:
                    result.description_calls += 1
            result.cam_time_ms += (perf_counter() - cam_started) * 1000
            result.cam_estimated_tokens += packet.estimated_tokens
            _admit(result, packet)
            content = packet.render()
            result.transcript.append(TranscriptMessage("CAM TOOL", "LIBRARIAN", content))
            messages.append(_tool_result_message(call, content))
        except (KeyError, ValueError) as exc:
            result.status = "tool_failure"
            result.error = str(exc)
            break
    else:
        result.status = "max_rounds"
        result.error = f"No valid submit_answer within {max_rounds} rounds"

    if memory_path.read_bytes() != memory_bytes:
        raise RuntimeError("Tool question harness modified memory.json")
    result.wall_time_ms = (perf_counter() - started) * 1000
    return result


def print_transcript(result: ToolQuestionResult) -> None:
    for message in result.transcript:
        print(f"\n{message.sender} -> {message.recipient}\n")
        print(message.content)
    print("\nFINAL ANSWER\n")
    print(result.answer or f"No answer ({result.error or result.status})")
    print(f"\nstatus={result.status}")
    print(f"LLM calls={result.llm_calls}")
    print(f"CAM tool calls={result.cam_tool_calls}")
    print(f"history calls={result.history_calls}")
    print(f"association calls={result.association_calls}")
    print(f"description calls={result.description_calls}")
    print(f"activations={result.activations}")
    print(f"CAM admitted estimated tokens={result.cam_estimated_tokens}")
    print(f"provider prompt tokens={result.provider_prompt_tokens}")
    print(f"provider completion tokens={result.provider_completion_tokens}")
    print(f"total provider tokens={result.provider_total_tokens}")
    print(f"provider retries={result.provider_retries}")
    if result.status == "tool_protocol_failure":
        print(
            "structured tool_calls field present="
            f"{result.structured_tool_calls_present}"
        )
    print(f"provider time={result.provider_time_ms:.3f} ms")
    print(f"CAM time={result.cam_time_ms:.3f} ms")
    print(f"wall time={result.wall_time_ms:.3f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tool-driven production CAM navigation.")
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--provider", choices=("groq", "llama-cpp"), default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--tool-choice", choices=("auto", "required"), default="auto")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--llama-model", default="cam-native-v1")
    parser.add_argument("--llama-timeout", type=float, default=120.0)
    parser.add_argument("--max-rounds", type=int, default=10)
    args = parser.parse_args()
    provider: ToolProvider
    if args.provider == "llama-cpp":
        provider = LlamaCppToolProvider(
            base_url=args.llama_url,
            model=args.llama_model,
            tool_choice=args.tool_choice,
            timeout_seconds=args.llama_timeout,
        )
    else:
        provider = GroqCamToolProvider(args.model, args.tool_choice)
    result = run_world_question_tools(
        args.world,
        args.question,
        provider_fn=provider,
        max_rounds=args.max_rounds,
    )
    print_transcript(result)


if __name__ == "__main__":
    main()
