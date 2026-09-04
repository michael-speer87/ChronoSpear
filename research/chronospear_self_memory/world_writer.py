"""Research harness separating a CAM Librarian from a general-purpose Writer."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from world_question import run_world_question

WRITER_SYSTEM_PROMPT = """You are a creative writer operating in a persistent fictional world.
You do not know established world canon unless it has been supplied in this conversation.
When useful established information is missing, call the memory tool with one
natural-language request for the canon useful to the requested scene.
Ask only for canon useful to the requested scene.
You may call memory again after evidence arrives.
Once you have enough canon, respond normally with only the final prose.
Do not invent established events, identities, relationships, or locations that
contradict or replace supplied canon. You may create dialogue, gestures, atmosphere,
phrasing, and immediate connective details that do not contradict canon."""

MEMORY_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "memory",
        "description": "Ask for established world information useful to the scene.",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "One natural-language request for world canon.",
                }
            },
            "required": ["request"],
            "additionalProperties": False,
        },
    },
}
WRITER_TOOLS: tuple[dict[str, object], ...] = (MEMORY_TOOL,)

FIRST_EXPERIMENT_PROMPT = (
    "Write a short interaction between Alric and the officer who gave him his "
    "first Royal Guard patrol assignment. Set it after the Old Quarry ambush, "
    "and have them briefly reflect on how much has changed since that first "
    "assignment."
)

LibrarianRunner = Callable[..., Any]


@dataclass(frozen=True)
class WriterToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class WriterProviderResult:
    content: str | None
    tool_calls: tuple[WriterToolCall, ...]
    usage: dict[str, object]


class WriterProvider(Protocol):
    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> WriterProviderResult: ...


@dataclass(frozen=True)
class WriterDecision:
    kind: str
    content: str
    tool_call: WriterToolCall | None = None


@dataclass(frozen=True)
class BoundaryMessage:
    sender: str
    recipient: str
    content: str
    query_number: int | None = None


@dataclass
class LibrarianTelemetry:
    queries: int = 0
    mini_igor_calls: int = 0
    cam_tool_calls: int = 0
    history_calls: int = 0
    association_calls: int = 0
    description_calls: int = 0
    cam_expansions: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider_time_ms: float = 0.0
    provider_retries: int = 0


@dataclass
class CamTelemetry:
    activation_count: int = 0
    estimated_packet_tokens: int = 0
    cam_time_ms: float = 0.0


@dataclass
class WriterTelemetry:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider_time_ms: float = 0.0
    provider_retries: int = 0


@dataclass
class WriterRunResult:
    request: str
    world: str
    status: str = "running"
    scene: str | None = None
    transcript: list[BoundaryMessage] = field(default_factory=list)
    writer: WriterTelemetry = field(default_factory=WriterTelemetry)
    librarian: LibrarianTelemetry = field(default_factory=LibrarianTelemetry)
    cam: CamTelemetry = field(default_factory=CamTelemetry)
    wall_time_ms: float = 0.0
    error: str | None = None


def parse_writer_response(response: WriterProviderResult) -> WriterDecision:
    content = response.content or ""
    if response.tool_calls:
        if len(response.tool_calls) != 1:
            raise ValueError("Writer must make at most one tool call per turn")
        if content.strip():
            raise ValueError("Writer cannot return prose and call a tool together")
        call = response.tool_calls[0]
        if call.name != "memory":
            raise ValueError(f"Writer called unavailable tool {call.name!r}")
        try:
            arguments = json.loads(call.arguments)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("memory tool arguments must be valid JSON") from exc
        if not isinstance(arguments, dict) or set(arguments) != {"request"}:
            raise ValueError("memory tool requires exactly one request argument")
        request = arguments["request"]
        if not isinstance(request, str) or not request.strip():
            raise ValueError("memory request must be a non-empty string")
        first_word = request.split(maxsplit=1)[0].upper()
        if first_word in {"ACTIVATE", "EXPAND"}:
            raise ValueError("memory requests cannot contain CAM control commands")
        return WriterDecision("memory", request, call)
    if not content.strip():
        raise ValueError("Writer must return final prose or call memory")
    return WriterDecision("scene", content)


class GroqWriterProvider:
    """Small OpenAI-compatible provider exposing only the local memory tool."""

    def __init__(self, model: str, tool_choice: str = "auto") -> None:
        if tool_choice not in {"auto", "required"}:
            raise ValueError("tool_choice must be 'auto' or 'required'")
        self._model = model
        self._tool_choice = tool_choice

    @staticmethod
    def _retry_delay(exc: urllib.error.HTTPError, body: str, attempt: int) -> float:
        retry_after = exc.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        match = re.search(
            r"Please try again in\s+([0-9]+(?:\.[0-9]+)?)s",
            body,
            flags=re.IGNORECASE,
        )
        if match:
            return float(match.group(1))
        return float(2**attempt)

    def __call__(
        self,
        messages: list[dict[str, object]],
        tools: tuple[dict[str, object], ...],
    ) -> WriterProviderResult:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY must be set for Groq")
        body = json.dumps(
            {
                "model": self._model,
                "messages": messages,
                "tools": list(tools),
                "tool_choice": self._tool_choice,
                "temperature": 0,
            }
        ).encode()
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChronoSpear-Research/2026-08-31",
            },
            method="POST",
        )
        retries = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode(errors="replace")
                if exc.code != 429 or retries >= 3:
                    raise RuntimeError(
                        f"Groq HTTP {exc.code}: {response_body}"
                    ) from exc
                delay = self._retry_delay(exc, response_body, retries)
                time.sleep(delay + 0.1)
                retries += 1
            except (urllib.error.URLError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Groq Writer request failed: {exc}") from exc
        message = payload["choices"][0]["message"]
        calls = tuple(
            WriterToolCall(
                call_id=call["id"],
                name=call["function"]["name"],
                arguments=call["function"]["arguments"],
            )
            for call in message.get("tool_calls", ())
        )
        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        usage["provider_retries"] = retries
        return WriterProviderResult(message.get("content"), calls, usage)


def format_canon_response(result: Any) -> str:
    addressable_ids = tuple(
        identifier
        for identifier in result.evidence_ids
        if identifier.casefold() != "none"
    )
    lines = [
        "CANON RESPONSE",
        "",
        "Librarian answer:",
        result.answer or f"Unavailable: {result.error or result.status}",
        "",
        "Evidence IDs:",
        ", ".join(addressable_ids) or "none",
        "",
        "Supporting evidence:",
    ]
    supporting = [
        result.admitted_evidence[identifier]
        for identifier in addressable_ids
        if identifier in result.admitted_evidence
    ]
    if supporting:
        lines.extend(f"- {record}" for record in supporting)
    elif not addressable_ids and result.admitted_descriptions:
        lines.extend(f"- DESCRIPTION {record}" for record in result.admitted_descriptions)
    elif addressable_ids:
        lines.append("- cited IDs were not present in admitted CAM evidence")
    else:
        lines.append("- none supplied")
    return "\n".join(lines)


def _usage_int(usage: dict[str, object], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _add_writer_usage(
    telemetry: WriterTelemetry,
    provider_result: WriterProviderResult,
    elapsed_ms: float,
) -> None:
    telemetry.calls += 1
    telemetry.prompt_tokens += _usage_int(provider_result.usage, "prompt_tokens")
    telemetry.completion_tokens += _usage_int(
        provider_result.usage, "completion_tokens"
    )
    telemetry.provider_time_ms += elapsed_ms
    telemetry.provider_retries += _usage_int(provider_result.usage, "provider_retries")


def _add_librarian_telemetry(
    result: WriterRunResult, librarian_result: Any
) -> None:
    result.librarian.queries += 1
    result.librarian.mini_igor_calls += librarian_result.llm_calls
    result.librarian.cam_expansions += getattr(librarian_result, "cam_expansions", 0)
    result.librarian.cam_tool_calls += getattr(librarian_result, "cam_tool_calls", 0)
    result.librarian.history_calls += getattr(librarian_result, "history_calls", 0)
    result.librarian.association_calls += getattr(
        librarian_result, "association_calls", 0
    )
    result.librarian.description_calls += getattr(
        librarian_result, "description_calls", 0
    )
    result.librarian.prompt_tokens += librarian_result.provider_prompt_tokens
    result.librarian.completion_tokens += librarian_result.provider_completion_tokens
    result.librarian.provider_time_ms += librarian_result.provider_time_ms
    result.librarian.provider_retries += getattr(
        librarian_result, "provider_retries", 0
    )
    result.cam.activation_count += getattr(
        librarian_result,
        "cam_activation_count",
        getattr(librarian_result, "activations", 0),
    )
    result.cam.estimated_packet_tokens += librarian_result.cam_estimated_tokens
    result.cam.cam_time_ms += librarian_result.cam_time_ms


def run_world_writer(
    world_path: str | Path,
    creative_request: str,
    *,
    writer_provider: WriterProvider,
    librarian_provider: Any,
    librarian_runner: LibrarianRunner = run_world_question,
    max_writer_turns: int = 5,
    max_librarian_queries: int = 4,
    max_librarian_rounds: int = 10,
) -> WriterRunResult:
    if max_writer_turns < 1 or max_librarian_queries < 0 or max_librarian_rounds < 1:
        raise ValueError("Writer and Librarian limits must be positive")
    start = perf_counter()
    path = Path(world_path)
    memory_path = path / "memory.json"
    memory_bytes = memory_path.read_bytes()
    result = WriterRunResult(request=creative_request, world=str(path))
    result.transcript.append(BoundaryMessage("USER", "WRITER", creative_request))
    writer_messages: list[dict[str, object]] = [
        {"role": "system", "content": WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": creative_request},
    ]

    for _turn in range(1, max_writer_turns + 1):
        provider_start = perf_counter()
        try:
            writer_response = writer_provider(writer_messages, WRITER_TOOLS)
        except RuntimeError as exc:
            result.status = "writer_provider_failure"
            result.error = str(exc)
            break
        _add_writer_usage(
            result.writer, writer_response, (perf_counter() - provider_start) * 1000
        )
        try:
            decision = parse_writer_response(writer_response)
        except ValueError as exc:
            result.status = "writer_protocol_failure"
            result.error = str(exc)
            result.transcript.append(
                BoundaryMessage("WRITER", "HARNESS", writer_response.content or "")
            )
            break

        if decision.kind == "scene":
            result.status = "scene"
            result.scene = decision.content
            result.transcript.append(
                BoundaryMessage("WRITER", "USER", decision.content)
            )
            break

        call = decision.tool_call
        if call is None:
            raise RuntimeError("memory decision is missing its tool call")
        writer_messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    }
                ],
            }
        )

        if result.librarian.queries >= max_librarian_queries:
            result.status = "librarian_query_limit"
            result.error = f"Writer exceeded {max_librarian_queries} Librarian queries"
            result.transcript.append(
                BoundaryMessage("WRITER", "MEMORY TOOL", decision.content)
            )
            break

        query_number = result.librarian.queries + 1
        result.transcript.append(
            BoundaryMessage(
                "WRITER", "MEMORY TOOL", decision.content, query_number
            )
        )
        librarian_result = librarian_runner(
            path,
            decision.content,
            provider_fn=librarian_provider,
            max_rounds=max_librarian_rounds,
        )
        _add_librarian_telemetry(result, librarian_result)
        if librarian_result.status == "provider_failure":
            result.status = "librarian_provider_failure"
            result.error = librarian_result.error
            break
        for message in librarian_result.transcript:
            if hasattr(message, "recipient"):
                sender = message.sender
                recipient = message.recipient
            else:
                sender = "CAM" if message.sender == "CAM" else "MINI-IGOR"
                recipient = "MINI-IGOR" if sender == "CAM" else "CAM"
            result.transcript.append(
                BoundaryMessage(sender, recipient, message.content, query_number)
            )
        canon_response = format_canon_response(librarian_result)
        result.transcript.append(
            BoundaryMessage("MEMORY TOOL", "WRITER", canon_response, query_number)
        )
        writer_messages.append(
            {
                "role": "tool",
                "tool_call_id": call.call_id,
                "name": "memory",
                "content": canon_response,
            }
        )
    else:
        result.status = "writer_turn_limit"
        result.error = f"Writer did not produce SCENE within {max_writer_turns} turns"

    if memory_path.read_bytes() != memory_bytes:
        raise RuntimeError("Librarian + Writer harness modified memory.json")
    result.wall_time_ms = (perf_counter() - start) * 1000
    return result


def print_writer_transcript(result: WriterRunResult) -> None:
    line = "=" * 60
    divider = "-" * 60
    print(line)
    print("CHRONOSPEAR LIBRARIAN + WRITER")
    print(line)
    for message in result.transcript:
        if message.sender == "WRITER" and message.recipient == "USER":
            continue
        if message.query_number and message.sender == "CAM":
            print(f"\nLIBRARIAN QUERY {message.query_number} <-> CAM")
        print(f"\n{message.sender} -> {message.recipient}\n")
        print(message.content)
        print(f"\n{divider}")
    print("\nWRITER FINAL SCENE\n")
    print(result.scene or f"No scene ({result.error or result.status})")
    print(f"\n{line}")
    print("Writer:")
    print(f"  calls={result.writer.calls}")
    print(f"  prompt_tokens={result.writer.prompt_tokens}")
    print(f"  completion_tokens={result.writer.completion_tokens}")
    print(f"  provider_time={result.writer.provider_time_ms:.3f} ms")
    print(f"  provider_retries={result.writer.provider_retries}")
    print("Librarian:")
    print(f"  queries={result.librarian.queries}")
    print(f"  LLM calls={result.librarian.mini_igor_calls}")
    print(f"  CAM tool calls={result.librarian.cam_tool_calls}")
    print(f"  history calls={result.librarian.history_calls}")
    print(f"  association calls={result.librarian.association_calls}")
    print(f"  description calls={result.librarian.description_calls}")
    print(f"  CAM expansions={result.librarian.cam_expansions}")
    print(f"  prompt_tokens={result.librarian.prompt_tokens}")
    print(f"  completion_tokens={result.librarian.completion_tokens}")
    print(f"  provider_time={result.librarian.provider_time_ms:.3f} ms")
    print(f"  provider_retries={result.librarian.provider_retries}")
    print("CAM:")
    print(f"  activation count={result.cam.activation_count}")
    print(f"  admitted estimated tokens={result.cam.estimated_packet_tokens}")
    print(f"  CAM time={result.cam.cam_time_ms:.3f} ms")
    print("Overall:")
    print(f"  status={result.status}")
    print(f"  wall time={result.wall_time_ms:.3f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the experimental production-CAM Librarian + Writer loop."
    )
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--prompt", default=FIRST_EXPERIMENT_PROMPT)
    parser.add_argument("--writer-model", default="openai/gpt-oss-20b")
    parser.add_argument(
        "--librarian-provider", choices=("groq", "llama-cpp"), default="groq"
    )
    parser.add_argument("--librarian-model", default="openai/gpt-oss-20b")
    parser.add_argument(
        "--librarian-tool-choice", choices=("auto", "required"), default="auto"
    )
    parser.add_argument(
        "--librarian-llama-url", default="http://127.0.0.1:8080/v1"
    )
    parser.add_argument("--librarian-llama-model", default="cam-native-v1")
    parser.add_argument("--librarian-llama-timeout", type=float, default=120.0)
    parser.add_argument("--max-writer-turns", type=int, default=5)
    parser.add_argument("--max-librarian-queries", type=int, default=4)
    parser.add_argument("--max-librarian-rounds", type=int, default=10)
    args = parser.parse_args()

    from llama_cpp_provider import LlamaCppToolProvider
    from world_question_tools import GroqCamToolProvider, run_world_question_tools

    if args.librarian_provider == "llama-cpp":
        librarian = LlamaCppToolProvider(
            base_url=args.librarian_llama_url,
            model=args.librarian_llama_model,
            timeout_seconds=args.librarian_llama_timeout,
            tool_choice=args.librarian_tool_choice,
        )
    else:
        librarian = GroqCamToolProvider(
            args.librarian_model,
            args.librarian_tool_choice,
        )
    result = run_world_writer(
        args.world,
        args.prompt,
        writer_provider=GroqWriterProvider(args.writer_model),
        librarian_provider=librarian,
        librarian_runner=run_world_question_tools,
        max_writer_turns=args.max_writer_turns,
        max_librarian_queries=args.max_librarian_queries,
        max_librarian_rounds=args.max_librarian_rounds,
    )
    print_writer_transcript(result)


if __name__ == "__main__":
    main()
