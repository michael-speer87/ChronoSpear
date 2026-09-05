"""Tool-driven question harness over the read-only production CAM adapter."""

from __future__ import annotations

import argparse
import json
import re
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

SYSTEM_PROMPT = """You are a Librarian navigating external world memory.
Use only world memory explicitly returned by the available tools. Do not guess
established world facts. Search for or activate relevant identities when needed.
For a question about a specific historical event, time, place, participant, action,
or relationship, prefer History that directly states the fact. Neighboring
Associations and unrelated History are not direct support. If relevant History
remains available, retrieve it before making an unsupported historical inference.
World truth and character knowledge are not automatically the same thing: shared
participation does not prove that each participant knew every other participant's
experience. Use submit_answer only when evidence is sufficient, citing exact
admitted evidence IDs. If reasonable retrieval cannot establish the answer, submit
an insufficient-evidence answer rather than guessing. You may suggest a missing
Identity; suggestions are advisory and never modify canonical memory."""

SEARCH_LIMIT = 5


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
        "search_memory",
        "Find bounded identity candidates by canonical name or synopsis. "
        "Results are orientation, not evidence.",
        {
            "query": {
                "type": "string",
                "description": "Text to find in identity names or synopses.",
            }
        },
        ["query"],
    ),
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
        "suggest_node",
        "Record a non-authoritative candidate Identity suggestion without changing CAM.",
        {
            "kind": {"type": "string", "enum": ["ENTITY", "PLACE", "DESCRIBER"]},
            "name": {"type": "string"},
            "reason": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
        ["kind", "name", "reason", "evidence_ids"],
    ),
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


@dataclass(frozen=True)
class RecentConversationTurn:
    user: str
    assistant: str


@dataclass(frozen=True)
class NodeSuggestion:
    kind: str
    name: str
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class LanguageHandle:
    kind: str
    name: str


@dataclass(frozen=True)
class LanguageMatch:
    phrase: str
    handles: tuple[LanguageHandle, ...]


@dataclass(frozen=True)
class WorldRecognition:
    """Shallow routing metadata from the existing deterministic Language Surface."""

    matched: bool
    targets: tuple[str, ...]
    ambiguous: bool

    def payload(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "targets": list(self.targets),
            "ambiguous": self.ambiguous,
        }


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
    searches: int = 0
    history_calls: int = 0
    association_calls: int = 0
    description_calls: int = 0
    activations: int = 0
    initial_activations: int = 0
    explicit_activations: int = 0
    node_suggestions: int = 0
    submit_attempts: int = 0
    language_matches: int = 0
    ambiguous_language_matches: int = 0
    unrecognized_query_phrases: int = 0
    recognized_handles: list[LanguageMatch] = field(default_factory=list)
    suggestions: list[NodeSuggestion] = field(default_factory=list)
    navigation_trace: list[str] = field(default_factory=list)
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


def _render_tool_packet(packet: ProductionMemoryPacket) -> str:
    stale = (
        "Use the active CAM-native protocol to request additional memory or answer. "
        "CAM supplies records mechanically; you decide what they mean for the question."
    )
    native = (
        "Use the supplied world memory to answer the question. If more memory is "
        "needed, use an available memory tool. Do not request memory already supplied. "
        "When supported, call submit_answer with exact supporting evidence IDs. "
        "Do not guess established facts."
    )
    return packet.render().replace(stale, native)


def _language_aliases(name: str) -> tuple[str, ...]:
    aliases = {name}
    words = name.split()
    if len(words) > 1 and words[0].casefold() == "the":
        aliases.add(" ".join(words[1:]))
    aliases.update(
        word
        for word in words
        if len(word) >= 4 and word.casefold() not in {"the"}
    )
    return tuple(sorted(aliases, key=lambda value: (-len(value), value.casefold())))


def _recognize_language(
    adapter: ProductionCamAdapter, question: str
) -> tuple[LanguageMatch, ...]:
    targets: dict[str, list[LanguageHandle]] = {}
    display: dict[str, str] = {}
    for identity in adapter.world.identities.all():
        handle = LanguageHandle(identity.kind.value, identity.name)
        for alias in _language_aliases(identity.name):
            folded = alias.casefold()
            targets.setdefault(folded, []).append(handle)
            display[folded] = alias

    hits: list[tuple[int, int, str]] = []
    lowered = question.casefold()
    for alias in targets:
        for match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered):
            hits.append((match.start(), match.end(), alias))
    hits.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    selected: list[tuple[int, int, str]] = []
    for hit in hits:
        start, end, _alias = hit
        if any(
            start < chosen_end and end > chosen_start
            for chosen_start, chosen_end, _ in selected
        ):
            continue
        selected.append(hit)
    selected.sort()

    recognized: list[LanguageMatch] = []
    seen: set[tuple[str, tuple[LanguageHandle, ...]]] = set()
    for _start, _end, alias in selected:
        handles = tuple(
            sorted(
                set(targets[alias]),
                key=lambda handle: (handle.name.casefold(), handle.kind),
            )
        )
        marker = alias, handles
        if marker in seen:
            continue
        seen.add(marker)
        recognized.append(LanguageMatch(display[alias], handles))
    return tuple(recognized)


def probe_world_recognition(
    world_path: str | Path, question: str
) -> WorldRecognition:
    """Recognize possible world handles without activation or factual retrieval."""

    adapter = ProductionCamAdapter(import_world(Path(world_path)))
    matches = _recognize_language(adapter, question)
    targets: list[str] = []
    for match in matches:
        for handle in match.handles:
            if handle.name not in targets:
                targets.append(handle.name)
    return WorldRecognition(
        matched=bool(targets),
        targets=tuple(targets),
        ambiguous=any(len(match.handles) > 1 for match in matches),
    )


def _render_recognized_handles(matches: tuple[LanguageMatch, ...]) -> list[str]:
    active = [match.handles[0] for match in matches if len(match.handles) == 1]
    ambiguous = [match for match in matches if len(match.handles) > 1]
    lines = ["Initial active memory handles:"]
    lines.extend(f"- {handle.kind} | {handle.name}" for handle in active)
    if not active:
        lines.append("- none")
    lines.extend(["", "Ambiguous recognized handles:"])
    if not ambiguous:
        lines.append("- none")
        return lines
    for match in ambiguous:
        lines.append(f"- {match.phrase} -> possible handles:")
        lines.extend(f"  - {handle.kind} | {handle.name}" for handle in match.handles)
    return lines


def _render_bootstrap(
    question: str,
    matches: tuple[LanguageMatch, ...],
    recent_context: tuple[RecentConversationTurn, ...],
) -> str:
    handles = "\n".join(_render_recognized_handles(matches))
    recent_lines = ["Recent conversation (orientation only, not canonical evidence):"]
    if recent_context:
        for turn in recent_context:
            recent_lines.extend(
                (f"User: {turn.user}", f"Smeagol: {turn.assistant}")
            )
    else:
        recent_lines.append("- none")
    recent = "\n".join(recent_lines)
    return f"""CHRONOSPEAR MEMORY SESSION

{recent}

Current question:
{question}

{handles}

No world facts have been retrieved yet.

Instructions:
Initial active handles are canonical navigation targets identified from the query.
They contain no retrieved world facts and are not evidence. Use description,
Association, or History tools to inspect only what you need. Do not call
search_memory for an identity already listed as an active memory handle. Use
search_memory only to locate an identity that is not recognized or addressable,
including when a phrase is ambiguous. Do not use search_memory as a relationship,
event, or multi-identity query engine. Do not guess established world facts. For
specific historical facts, retrieve directly supporting History rather than relying on neighboring
Associations or unrelated History. World truth and character knowledge are not
automatically the same thing. When evidence is sufficient, use submit_answer with
exact admitted evidence IDs. If reasonable retrieval cannot establish the answer,
submit an insufficient-evidence answer. You may suggest an apparently missing
Identity; suggestions never modify CAM."""


def _single_string_argument(
    arguments: dict[str, object], key: str, tool_name: str
) -> str:
    if set(arguments) != {key} or not isinstance(arguments[key], str):
        raise ValueError(f"{tool_name} requires exactly one string {key}")
    value = arguments[key].strip()
    if not value:
        raise ValueError(f"{tool_name} {key} cannot be blank")
    return value


def _search_memory(adapter: ProductionCamAdapter, query: str) -> str:
    folded = query.casefold()
    matches = [
        identity
        for identity in adapter.world.identities.all()
        if folded in identity.name.casefold() or folded in identity.synopsis.casefold()
    ]
    matches.sort(
        key=lambda identity: (
            identity.name.casefold(),
            identity.kind.value,
            str(identity.identity_id),
        )
    )
    selected = matches[:SEARCH_LIMIT]
    if not selected:
        return f"MEMORY SEARCH\nQuery: {query}\nResults: 0\n- none"
    lines = ["MEMORY SEARCH", f"Query: {query}", f"Results: {len(selected)}"]
    lines.extend(
        f"- {identity.kind.value} | {identity.name} | {identity.synopsis or '(no synopsis)'}"
        for identity in selected
    )
    if len(matches) > SEARCH_LIMIT:
        lines.append(f"- {len(matches) - SEARCH_LIMIT} additional matches omitted")
    lines.append(
        "Search orientation is not canonical evidence. "
        "Activate an identity to retrieve memory."
    )
    return "\n".join(lines)


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


def _assistant_response_message(response: ToolResponse) -> dict[str, object]:
    message: dict[str, object] = {
        "role": "assistant",
        "content": response.content,
    }
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in response.tool_calls
        ]
    return message


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
    recent_context: tuple[RecentConversationTurn, ...] = (),
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
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result.status = "cam_initial_failure"
        result.error = str(exc)
        result.wall_time_ms = (perf_counter() - started) * 1000
        return result
    result.cam_time_ms += (perf_counter() - cam_started) * 1000
    matches = _recognize_language(adapter, question)
    result.recognized_handles.extend(matches)
    result.language_matches = sum(len(match.handles) == 1 for match in matches)
    result.ambiguous_language_matches = sum(
        len(match.handles) > 1 for match in matches
    )
    result.unrecognized_query_phrases = 0 if matches else 1
    for match in matches:
        names = " | ".join(handle.name for handle in match.handles)
        result.navigation_trace.append(f"LANGUAGE: {match.phrase} -> {names}")
        if len(match.handles) == 1:
            canonical = match.handles[0].name
            session.surfaced_concepts.add(canonical)
            result.initial_activations += 1
            result.activations += 1
            result.navigation_trace.append(f"LANGUAGE-ACTIVATE: {canonical}")
    opening_text = _render_bootstrap(question, matches, recent_context)
    result.transcript.append(TranscriptMessage("HARNESS", "LIBRARIAN", opening_text))
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
            if not response.tool_calls:
                correction = (
                    "No tool call was made. Use an available memory tool if more "
                    "evidence is needed, or call submit_answer when the current "
                    "evidence supports the answer."
                )
                messages.append(_assistant_response_message(response))
                messages.append({"role": "user", "content": correction})
            else:
                correction = "Make exactly one tool call per Librarian turn."
                messages.append(_assistant_response_message(response))
                for rejected_call in response.tool_calls:
                    messages.append(
                        _tool_result_message(rejected_call, correction)
                    )
            result.transcript.append(
                TranscriptMessage("HARNESS", "LIBRARIAN", correction)
            )
            continue
        call = response.tool_calls[0]
        result.cam_tool_calls += 1
        messages.append(_assistant_call_message(call))
        try:
            arguments = _arguments(call)
            if call.name == "submit_answer":
                result.submit_attempts += 1
                result.navigation_trace.append("submit_answer(...)")
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

            if call.name == "search_memory":
                query = _single_string_argument(arguments, "query", "search_memory")
                result.searches += 1
                result.navigation_trace.append(f"search_memory({query!r})")
                result.transcript.append(
                    TranscriptMessage(
                        "LIBRARIAN", "CAM TOOL", f"search_memory(query={query!r})"
                    )
                )
                cam_started = perf_counter()
                content = _search_memory(adapter, query)
                result.cam_time_ms += (perf_counter() - cam_started) * 1000
                result.transcript.append(
                    TranscriptMessage("CAM TOOL", "LIBRARIAN", content)
                )
                messages.append(_tool_result_message(call, content))
                continue

            if call.name == "suggest_node":
                if set(arguments) != {"kind", "name", "reason", "evidence_ids"}:
                    raise ValueError(
                        "suggest_node requires kind, name, reason, and evidence_ids"
                    )
                kind = arguments["kind"]
                name = arguments["name"]
                reason = arguments["reason"]
                ids = arguments["evidence_ids"]
                if kind not in {"ENTITY", "PLACE", "DESCRIBER"}:
                    raise ValueError("suggest_node kind must be an Identity kind")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("suggest_node name must be non-empty")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("suggest_node reason must be non-empty")
                if not isinstance(ids, list) or not all(
                    isinstance(item, str) for item in ids
                ):
                    raise ValueError("suggest_node evidence_ids must be a string list")
                unadmitted = [
                    item for item in ids if item not in result.admitted_evidence
                ]
                if unadmitted:
                    raise ValueError("unadmitted evidence IDs: " + ", ".join(unadmitted))
                suggestion = NodeSuggestion(
                    kind=kind,
                    name=name.strip(),
                    reason=reason.strip(),
                    evidence_ids=tuple(ids),
                )
                result.suggestions.append(suggestion)
                result.node_suggestions += 1
                result.navigation_trace.append(
                    f"suggest_node(kind={kind!r}, name={suggestion.name!r})"
                )
                request = (
                    f"suggest_node(kind={kind!r}, name={suggestion.name!r})"
                )
                result.transcript.append(
                    TranscriptMessage("LIBRARIAN", "CAM TOOL", request)
                )
                content = "Node suggestion recorded for review; canonical CAM is unchanged."
                result.transcript.append(
                    TranscriptMessage("CAM TOOL", "LIBRARIAN", content)
                )
                messages.append(_tool_result_message(call, content))
                continue

            name = _name_argument(arguments)
            result.navigation_trace.append(f"{call.name}({name!r})")
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
                result.explicit_activations += 1
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
            content = _render_tool_packet(packet)
            result.transcript.append(TranscriptMessage("CAM TOOL", "LIBRARIAN", content))
            messages.append(_tool_result_message(call, content))
        except (KeyError, ValueError) as exc:
            content = f"Tool unavailable or invalid: {exc}"
            result.transcript.append(
                TranscriptMessage("CAM TOOL", "LIBRARIAN", content)
            )
            messages.append(_tool_result_message(call, content))
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
    print(f"searches={result.searches}")
    print(f"history calls={result.history_calls}")
    print(f"association calls={result.association_calls}")
    print(f"description calls={result.description_calls}")
    print(f"activations={result.activations}")
    print(f"initial activations={result.initial_activations}")
    print(f"explicit activations={result.explicit_activations}")
    print(f"node suggestions={result.node_suggestions}")
    print(f"submit attempts={result.submit_attempts}")
    print(f"language matches={result.language_matches}")
    print(f"ambiguous language matches={result.ambiguous_language_matches}")
    print(f"unrecognized query phrases={result.unrecognized_query_phrases}")
    print(f"CAM admitted estimated tokens={result.cam_estimated_tokens}")
    print(f"provider prompt tokens={result.provider_prompt_tokens}")
    print(f"provider completion tokens={result.provider_completion_tokens}")
    print(f"total provider tokens={result.provider_total_tokens}")
    print(f"provider retries={result.provider_retries}")
    if result.structured_tool_calls_present is not None:
        print(
            "structured tool_calls field present="
            f"{result.structured_tool_calls_present}"
        )
    print(f"provider time={result.provider_time_ms:.3f} ms")
    print(f"CAM time={result.cam_time_ms:.3f} ms")
    print(f"wall time={result.wall_time_ms:.3f} ms")
    print("navigation trace:")
    for index, operation in enumerate(result.navigation_trace, start=1):
        print(f"  {index}. {operation}")


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
