"""Experimental general chatbot routing fictional canon through Smeagol."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Protocol

from llama_cpp_provider import LlamaCppToolProvider
from world_question_tools import (
    GroqCamToolProvider,
    ToolProvider,
    ToolQuestionResult,
    ToolResponse,
    WorldRecognition,
    probe_world_recognition,
    run_world_question_tools,
)
from world_writer import GroqWriterProvider

from chronospear.world_import import import_world

CHAT_TURN_LIMIT = 4
SYSTEM_PROMPT = """You are the conversational intelligence for ChronoSpear, an
AI-assisted living-world and TTRPG memory system. CAM means Chrono Associative
Memory and is authoritative persistent memory for the loaded fictional world. It
represents Identity Nodes, Associations, and immutable Historical Occurrences.
WorldTime is its canonical temporal coordinate; deterministic Calendar conversion
is separate engine infrastructure. Current Identity Node kinds are Entity, Place,
and Describer. Associations are semantic relationships between Identity Nodes.
Historical Occurrences are immutable objective events with WorldTime and event
context; they establish when meaningful changes happened. Association meaning is
semantic and History establishes when it applied; do not invent mutable Association
status objects. Do not invent AbilityNode, StateProperty, PropertyNode, or other CAM
object types. A meaningful concept that is neither Entity nor Place is generally a
Describer under the current model. Smeagol is the specialist intelligence that
navigates CAM and is limited to what CAM establishes. Recent conversation is
orientation, not canonical truth.

Answer ChronoSpear system questions from this brief and ordinary conversation
directly. For fictional-world facts, call ask_smeagol; never invent, override, or
supplement Smeagol's answer from model memory or web results. Preserve Smeagol's
uncertainty unless explicitly asked for clearly labeled non-canon speculation. For
current external facts call web_search. Web results concern external reality only
and never modify fictional canon. Mixed questions may call both tools. Formulate
explicit Smeagol requests using conversational context when useful. Tool use is
optional. Shallow CAM recognition metadata only indicates possible fictional-world
subjects: for factual claims about a recognized target, use ask_smeagol rather than
web search. A negative match does not prove that a subject is absent from the world.

Existing CAM content is canon. Your suggestions are non-canonical proposals. Only
a future explicit approval/write boundary may turn a proposal into canon. When the
user requests a suggestion, possibility, hypothetical, future event, possible
Historical Occurrence, Association, Node, or creative world addition, use Smeagol
when relevant canon is needed, then generate the proposal yourself. Clearly label
it non-canon, never imply CAM already contains it, and never mutate CAM. Smeagol
answers what is true; you may propose what could be true; a future approval boundary
decides what becomes true. For CAM design advice, use only the established object
model above and distinguish current CAM facts from what the user plans to add."""

SYSTEM_PROMPT += """

If a creative request involves a recognized, unambiguous fictional-world identity,
you must obtain relevant canonical context from Smeagol before proposing content.
Recognition tells you who belongs to the world; Smeagol tells you what is true;
only then should you imagine what could happen. Do not invent established backstory
to support a proposal. Do not assign WorldTime, SystemTime, or a calendar date unless
the user explicitly requests timing or date placement."""


def _tool(name: str, description: str, argument: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {argument: {"type": "string"}},
                "required": [argument],
                "additionalProperties": False,
            },
        },
    }


OUTER_TOOLS = (
    _tool("ask_smeagol", "Ask the authoritative fictional-world specialist.", "request"),
    _tool("web_search", "Search current external reality when configured.", "query"),
)


@dataclass(frozen=True)
class WebSearchResult:
    status: str
    content: str


class WebSearchProvider(Protocol):
    def search(self, query: str) -> WebSearchResult: ...


class UnavailableWebSearchProvider:
    def search(self, query: str) -> WebSearchResult:
        del query
        return WebSearchResult(
            "unavailable", "I don't currently have a configured live web-search provider."
        )


@dataclass(frozen=True)
class ChatTurn:
    user: str
    assistant: str


@dataclass
class ChatResult:
    question: str
    status: str = "running"
    answer: str | None = None
    trace: list[str] = field(default_factory=list)
    smeagol_results: list[ToolQuestionResult] = field(default_factory=list)
    outer_calls: int = 0
    outer_prompt_tokens: int = 0
    outer_completion_tokens: int = 0
    outer_retries: int = 0
    smeagol_queries: int = 0
    web_searches: int = 0
    wall_time_ms: float = 0.0
    error: str | None = None
    recognition: WorldRecognition | None = None


def _usage(usage: dict[str, object], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _argument(arguments: str, key: str) -> str:
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("outer tool arguments must be valid JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {key}:
        raise ValueError(f"outer tool requires exactly one {key}")
    value = parsed[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"outer tool {key} must be a non-empty string")
    return value.strip()


def _assistant_message(response: ToolResponse) -> dict[str, object]:
    calls = response.tool_calls
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    }


def _smeagol_payload(result: ToolQuestionResult) -> str:
    grounded = bool(result.evidence_ids or result.admitted_descriptions)
    return json.dumps(
        {"status": result.status, "answer": result.answer, "grounded": grounded},
        ensure_ascii=False,
    )


def _usable_smeagol_result(result: ToolQuestionResult) -> bool:
    return result.status == "answered" and bool((result.answer or "").strip())


SmeagolRunner = Callable[..., ToolQuestionResult]
RecognitionProbe = Callable[[str | Path, str], WorldRecognition]


def _requests_proposal(question: str) -> bool:
    normalized = question.casefold()
    return any(
        marker in normalized
        for marker in (
            "suggest",
            "proposal",
            "propose",
            "possible",
            "possibility",
            "could happen",
            "what could",
            "hypothetical",
            "idea for",
        )
    )


def _grounding_request(targets: tuple[str, ...]) -> str:
    joined = " and ".join(targets)
    return (
        f"What canonical information about {joined} is relevant to proposing "
        "possible new world content involving them? Include established identity, "
        "important traits, abilities, relationships, and relevant history. "
        "Do not invent anything."
    )


def run_chat_turn(
    world_path: str | Path,
    question: str,
    *,
    outer_provider: ToolProvider,
    smeagol_provider: ToolProvider,
    web_provider: WebSearchProvider,
    recent_context: tuple[ChatTurn, ...] = (),
    smeagol_runner: SmeagolRunner = run_world_question_tools,
    recognition_probe: RecognitionProbe = probe_world_recognition,
    max_rounds: int = 8,
    max_smeagol_rounds: int = 10,
) -> ChatResult:
    started = perf_counter()
    result = ChatResult(question)
    proposal_requested = _requests_proposal(question)
    try:
        recognition = recognition_probe(world_path, question)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result.status, result.error = "recognition_failure", str(exc)
        result.wall_time_ms = (perf_counter() - started) * 1000
        return result
    result.recognition = recognition
    grounding_required = bool(
        proposal_requested
        and recognition.matched
        and not recognition.ambiguous
        and recognition.targets
    )
    grounding_complete = False
    targets = ", ".join(recognition.targets) or "none"
    result.trace.append(
        f"CAM-RECOGNITION: matched={str(recognition.matched).lower()} "
        f"targets={targets} ambiguous={str(recognition.ambiguous).lower()}"
    )
    if grounding_required:
        result.trace.append("GROUNDING-REQUIRED: recognized world proposal")
    context = "\n".join(
        f"User: {turn.user}\nAssistant: {turn.assistant}" for turn in recent_context
    ) or "- none"
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Recent conversation:\n{context}\n\n"
                "Shallow CAM recognition (routing metadata only; not world facts):\n"
                f"{json.dumps(recognition.payload(), ensure_ascii=False)}\n\n"
                f"Current question:\n{question}"
            ),
        },
    ]
    unresolved_world_answer: str | None = None
    for _ in range(max_rounds):
        try:
            response = outer_provider(messages, OUTER_TOOLS)
        except RuntimeError as exc:
            result.status, result.error = "provider_failure", str(exc)
            break
        result.outer_calls += 1
        result.outer_prompt_tokens += _usage(response.usage, "prompt_tokens")
        result.outer_completion_tokens += _usage(response.usage, "completion_tokens")
        result.outer_retries += _usage(response.usage, "provider_retries")
        if not response.tool_calls:
            content = (response.content or "").strip()
            if not content:
                result.status, result.error = "protocol_failure", "empty outer response"
            else:
                if grounding_required and not grounding_complete:
                    request = _grounding_request(recognition.targets)
                    call_id = "required-smeagol-grounding"
                    result.trace.append(f"ask_smeagol({request!r})")
                    specialist = smeagol_runner(
                        world_path,
                        request,
                        provider_fn=smeagol_provider,
                        max_rounds=max_smeagol_rounds,
                    )
                    result.smeagol_queries += 1
                    result.smeagol_results.append(specialist)
                    if not _usable_smeagol_result(specialist):
                        result.status = "grounding_failure"
                        result.error = (
                            "I couldn't retrieve the recognized target's current CAM "
                            "context, so I won't invent a character-specific proposal "
                            "without grounding."
                        )
                        break
                    grounding_complete = True
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": "ask_smeagol",
                                            "arguments": json.dumps(
                                                {"request": request}, ensure_ascii=False
                                            ),
                                        },
                                    }
                                ],
                            },
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": "ask_smeagol",
                                "content": _smeagol_payload(specialist),
                            },
                        ]
                    )
                    continue
                if proposal_requested and recognition.ambiguous:
                    choices = ", ".join(recognition.targets)
                    content = (
                        f"The world reference is ambiguous ({choices}). "
                        "Please clarify which target the proposal should involve."
                    )
                if (
                    unresolved_world_answer is not None
                    and not proposal_requested
                    and "speculat" not in question.casefold()
                ):
                    content = unresolved_world_answer
                elif proposal_requested and not recognition.ambiguous:
                    labels = ("non-canon", "proposal", "suggestion", "possibility")
                    if not any(label in content.casefold() for label in labels):
                        content = f"Non-canonical proposal: {content}"
                    qualifier = "grounded " if grounding_required else ""
                    result.trace.append(
                        f"OUTER: generated {qualifier}non-canonical proposal"
                    )
                result.status, result.answer = "answered", content
            break
        if len(response.tool_calls) != 1 or (response.content or "").strip():
            result.status = "protocol_failure"
            result.error = "outer chatbot must make one tool call or answer normally"
            break
        call = response.tool_calls[0]
        messages.append(_assistant_message(response))
        try:
            if call.name == "ask_smeagol":
                request = _argument(call.arguments, "request")
                result.trace.append(f"ask_smeagol({request!r})")
                specialist = smeagol_runner(
                    world_path,
                    request,
                    provider_fn=smeagol_provider,
                    max_rounds=max_smeagol_rounds,
                )
                result.smeagol_queries += 1
                result.smeagol_results.append(specialist)
                if grounding_required and not _usable_smeagol_result(specialist):
                    result.status = "grounding_failure"
                    result.error = (
                        "I couldn't retrieve the recognized target's current CAM "
                        "context, so I won't invent a character-specific proposal "
                        "without grounding."
                    )
                    break
                if _usable_smeagol_result(specialist):
                    grounding_complete = True
                if not (specialist.evidence_ids or specialist.admitted_descriptions):
                    unresolved_world_answer = (
                        specialist.answer
                        or specialist.error
                        or "Smeagol could not establish the requested world fact."
                    )
                content = _smeagol_payload(specialist)
            elif call.name == "web_search":
                query = _argument(call.arguments, "query")
                result.trace.append(f"web_search({query!r})")
                result.web_searches += 1
                external = web_provider.search(query)
                content = json.dumps(
                    {"status": external.status, "result": external.content},
                    ensure_ascii=False,
                )
            else:
                raise ValueError(f"unknown outer tool {call.name!r}")
        except ValueError as exc:
            content = f"Tool unavailable or invalid: {exc}"
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.call_id,
                "name": call.name,
                "content": content,
            }
        )
    else:
        result.status, result.error = "max_rounds", "outer chatbot exhausted rounds"
    result.wall_time_ms = (perf_counter() - started) * 1000
    return result


HELP = """Commands: /help, /trace on, /trace off, /stats, /clear, /world,
  /smeagol <question>, /quit, /exit"""


class ChronoSpearChat:
    def __init__(
        self,
        world_path: str | Path,
        *,
        outer_provider: ToolProvider,
        smeagol_provider: ToolProvider,
        web_provider: WebSearchProvider,
        outer_model: str,
        provider_name: str,
        smeagol_runner: SmeagolRunner = run_world_question_tools,
    ) -> None:
        self.world_path = Path(world_path)
        self.outer_provider = outer_provider
        self.smeagol_provider = smeagol_provider
        self.web_provider = web_provider
        self.outer_model = outer_model
        self.provider_name = provider_name
        self.smeagol_runner = smeagol_runner
        self.recent: list[ChatTurn] = []
        self.last: ChatResult | None = None
        self.trace = False

    def run(
        self,
        input_fn: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
    ) -> None:
        output("=" * 60)
        output("CHRONOSPEAR CHAT")
        output("=" * 60)
        output(f"World: {self.world_path}")
        output("World Memory Specialist: Smeagol")
        output(f"Provider: {self.provider_name}")
        output(f"Model: {self.outer_model}")
        output("\nType /help for commands.")
        while True:
            try:
                text = input_fn("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                output("\nChronoSpear Chat ended.")
                return
            if not text:
                continue
            if text.casefold() in {"/quit", "/exit"}:
                output("ChronoSpear Chat ended.")
                return
            if text.startswith("/"):
                self._command(text, output)
                continue
            result = run_chat_turn(
                self.world_path,
                text,
                outer_provider=self.outer_provider,
                smeagol_provider=self.smeagol_provider,
                web_provider=self.web_provider,
                recent_context=tuple(self.recent),
                smeagol_runner=self.smeagol_runner,
            )
            self._show(text, result, output)

    def _show(self, question: str, result: ChatResult, output: Callable[[str], None]) -> None:
        self.last = result
        if result.status == "answered" and result.answer:
            output(f"ChronoSpear > {result.answer}")
            self.recent.append(ChatTurn(question, result.answer))
            self.recent = self.recent[-CHAT_TURN_LIMIT:]
        else:
            output(f"ChronoSpear > Query failed ({result.status}): {result.error}")
        if self.trace:
            output("[outer trace]")
            for item in result.trace:
                output(item)
            for specialist in result.smeagol_results:
                output("[smeagol trace]")
                for item in specialist.navigation_trace:
                    output(item)

    def _command(self, text: str, output: Callable[[str], None]) -> None:
        normalized = " ".join(text.casefold().split())
        if normalized == "/help":
            output(HELP)
        elif normalized == "/trace on":
            self.trace = True
            output("Trace enabled.")
        elif normalized == "/trace off":
            self.trace = False
            output("Trace disabled.")
        elif normalized == "/stats":
            if self.last is None:
                output("No query has run yet.")
            else:
                output(
                    f"status={self.last.status} outer_calls={self.last.outer_calls} "
                    f"smeagol_queries={self.last.smeagol_queries} "
                    f"web_searches={self.last.web_searches} "
                    f"wall_time={self.last.wall_time_ms:.3f} ms"
                )
        elif normalized == "/clear":
            self.recent.clear()
            self.last = None
            output("Recent conversation and last-query state cleared.")
        elif normalized == "/world":
            world = import_world(self.world_path)
            output(
                f"World: {self.world_path} | identities={len(world.identities.all())} "
                f"associations={len(world.associations.all())} "
                f"history={len(world.occurrences.all())}"
            )
        elif normalized.startswith("/smeagol "):
            request = text.split(maxsplit=1)[1]
            specialist = self.smeagol_runner(
                self.world_path, request, provider_fn=self.smeagol_provider
            )
            output(f"Smeagol > {specialist.answer or specialist.error or specialist.status}")
            if self.trace:
                output("[smeagol trace]")
                for item in specialist.navigation_trace:
                    output(item)
        else:
            output(f"Unknown command: {text}. Type /help for commands.")


def _provider(kind: str, model: str, tool_choice: str, llama_url: str) -> ToolProvider:
    if kind == "llama-cpp":
        return LlamaCppToolProvider(
            base_url=llama_url, model=model, tool_choice=tool_choice
        )
    return GroqCamToolProvider(model, tool_choice)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the general ChronoSpear chatbot.")
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--provider", choices=("groq", "llama-cpp"), default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--smeagol-provider", choices=("groq", "llama-cpp"), default="groq")
    parser.add_argument("--smeagol-model", default="openai/gpt-oss-20b")
    parser.add_argument("--smeagol-tool-choice", choices=("auto", "required"), default="required")
    parser.add_argument("--smeagol-llama-url", default="http://127.0.0.1:8080/v1")
    args = parser.parse_args()
    outer: ToolProvider
    if args.provider == "llama-cpp":
        outer = _provider(args.provider, args.model, "auto", args.llama_url)
    else:
        outer = GroqWriterProvider(args.model, "auto")
    smeagol = _provider(
        args.smeagol_provider,
        args.smeagol_model,
        args.smeagol_tool_choice,
        args.smeagol_llama_url,
    )
    ChronoSpearChat(
        args.world,
        outer_provider=outer,
        smeagol_provider=smeagol,
        web_provider=UnavailableWebSearchProvider(),
        outer_model=args.model,
        provider_name=args.provider,
    ).run()


if __name__ == "__main__":
    main()
