from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from chronospear.experiments.cam_llm import (
    ContextMetrics,
    ExperimentLimits,
    ExperimentProtocolError,
)

Interpretation = Literal["context_request", "conclusion", "unrecognized"]


def _metrics(records: tuple[str, ...]) -> ContextMetrics:
    rendered = "\n".join(records)
    return ContextMetrics(len(records), len(rendered), len(rendered.encode("utf-8")))


def _surface_record(record: str) -> str:
    if record.startswith("NODE "):
        parts = record.split(" | ", maxsplit=3)
        if len(parts) == 4:
            return " | ".join(parts[1:])
    if record.startswith("ASSOC "):
        parts = record.split(" | ", maxsplit=1)
        if len(parts) == 2:
            return parts[1]
    return record


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class NaturalLanguageProviderRequest:
    call_number: int
    messages: tuple[ConversationMessage, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NaturalLanguageProviderResponse:
    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    provider_latency_seconds: float | None = None
    wall_latency_seconds: float | None = None


NaturalLanguageProvider = Callable[
    [NaturalLanguageProviderRequest], NaturalLanguageProviderResponse
]


@dataclass(frozen=True, slots=True)
class NaturalResolution:
    activations: tuple[str, ...]
    added_evidence: tuple[str, ...]


class NaturalLanguageResolver:
    """Fixture-only semantic resolver with no general CAM query authority."""

    __slots__ = ("_equipment_evidence", "_location_evidence")

    def __init__(
        self,
        *,
        location_evidence: tuple[str, ...],
        equipment_evidence: tuple[str, ...],
    ) -> None:
        self._location_evidence = location_evidence
        self._equipment_evidence = equipment_evidence

    def resolve(
        self,
        request: str,
        *,
        seen_evidence: frozenset[str],
        remaining_records: int,
        remaining_utf8_bytes: int,
    ) -> NaturalResolution:
        normalized = request.casefold()
        candidates: list[tuple[str, tuple[str, ...]]] = []
        location_words = (
            "where",
            "located",
            "location",
            "based",
            "whereabouts",
            "resides",
            "city",
            "find",
            "address",
            "stationed",
        )
        equipment_words = ("equipment", "carry", "carries", "owns", "possession")
        if ("archivist sol" in normalized or " sol" in normalized) and any(
            word in normalized for word in location_words
        ):
            candidates.append(("Archivist Sol location", self._location_evidence))
        if "nera" in normalized and any(word in normalized for word in equipment_words):
            candidates.append(("Nera equipment", self._equipment_evidence))

        activations: list[str] = []
        added: list[str] = []
        current_seen = set(seen_evidence)
        for activation, evidence in candidates:
            activations.append(activation)
            novel = tuple(item for item in evidence if item not in current_seen)
            metrics = _metrics(novel)
            if (
                metrics.record_count > remaining_records
                or metrics.utf8_bytes > remaining_utf8_bytes
            ):
                continue
            added.extend(novel)
            current_seen.update(novel)
            remaining_records -= metrics.record_count
            remaining_utf8_bytes -= metrics.utf8_bytes
        return NaturalResolution(tuple(activations), tuple(added))


@dataclass(frozen=True, slots=True)
class NaturalCallRecord:
    call_number: int
    evidence_before: tuple[str, ...]
    context: ContextMetrics
    raw_response: str
    interpretation: Interpretation
    context_request: str | None
    activations: tuple[str, ...]
    added_evidence: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    model: str | None
    provider_latency_seconds: float | None
    wall_latency_seconds: float | None


@dataclass(frozen=True, slots=True)
class NaturalExperimentReport:
    action: str
    initial_context: ContextMetrics
    provider_calls: int
    expansion_rounds: int
    calls: tuple[NaturalCallRecord, ...]
    context_requests: tuple[str, ...]
    final_conclusion: str | None
    conclusion_supported: bool
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_provider_latency_seconds: float | None
    total_wall_latency_seconds: float | None


def _looks_like_request(text: str) -> bool:
    normalized = text.casefold()
    return text.rstrip().endswith("?") or any(
        phrase in normalized
        for phrase in (
            "i need",
            "need to know",
            "more information",
            "tell me",
            "can you provide",
            "what is",
            "where is",
            "who is",
        )
    )


def _based_in_destinations(evidence: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        record.split("--BASED_IN-->", maxsplit=1)[1].strip().casefold()
        for record in evidence
        if "--BASED_IN-->" in record
    )


def _looks_like_conclusion(text: str, evidence: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    candidate_destinations = tuple(
        record.split(" | ")[1].casefold()
        for record in evidence
        if record.startswith("PLACE | ") and len(record.split(" | ")) >= 2
    ) + _based_in_destinations(evidence)
    return "should travel" in normalized or any(
        destination in normalized for destination in candidate_destinations
    )


def _conclusion_is_supported(text: str, evidence: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(
        destination in normalized for destination in _based_in_destinations(evidence)
    )


def _sum_optional(values: tuple[int | None, ...]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _sum_optional_float(values: tuple[float | None, ...]) -> float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def run_natural_language_experiment(
    *,
    action: str,
    initial_evidence: tuple[str, ...],
    resolver: NaturalLanguageResolver,
    provider: NaturalLanguageProvider,
    limits: ExperimentLimits | None = None,
) -> NaturalExperimentReport:
    """Run one bounded natural-language context-expansion experiment."""

    active_limits = limits or ExperimentLimits()
    surfaced_initial = tuple(_surface_record(record) for record in initial_evidence)
    evidence = list(surfaced_initial)
    messages: list[ConversationMessage] = [
        ConversationMessage(
            "user",
            f"ACTION\n{action}\n\nBOUNDED CAM EVIDENCE\n" + "\n".join(evidence),
        )
    ]
    calls: list[NaturalCallRecord] = []
    requests: list[str] = []
    expansion_rounds = 0
    added_records = 0
    added_bytes = 0
    maximum_calls = active_limits.max_expansion_rounds + 1
    final_conclusion: str | None = None
    conclusion_supported = False

    while len(calls) < maximum_calls:
        call_number = len(calls) + 1
        response = provider(
            NaturalLanguageProviderRequest(call_number, tuple(messages), tuple(evidence))
        )
        raw = response.raw_text.strip()
        resolution = resolver.resolve(
            raw,
            seen_evidence=frozenset(evidence),
            remaining_records=active_limits.max_added_records - added_records,
            remaining_utf8_bytes=active_limits.max_added_utf8_bytes - added_bytes,
        )
        if resolution.activations or _looks_like_request(raw):
            interpretation: Interpretation = "context_request"
            context_request = raw
            requests.append(raw)
        elif _looks_like_conclusion(raw, tuple(evidence)):
            interpretation = "conclusion"
            context_request = None
        else:
            interpretation = "unrecognized"
            context_request = None

        calls.append(
            NaturalCallRecord(
                call_number=call_number,
                evidence_before=tuple(evidence),
                context=_metrics(tuple(evidence)),
                raw_response=raw,
                interpretation=interpretation,
                context_request=context_request,
                activations=resolution.activations,
                added_evidence=resolution.added_evidence,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model=response.model,
                provider_latency_seconds=response.provider_latency_seconds,
                wall_latency_seconds=response.wall_latency_seconds,
            )
        )

        if interpretation == "conclusion":
            if len(raw) > active_limits.max_conclusion_characters:
                raise ExperimentProtocolError(
                    "Provider conclusion exceeds the compactness limit."
                )
            final_conclusion = raw
            conclusion_supported = _conclusion_is_supported(raw, tuple(evidence))
            break
        if call_number >= maximum_calls:
            break

        expansion_rounds += 1
        evidence.extend(resolution.added_evidence)
        added = _metrics(resolution.added_evidence)
        added_records += added.record_count
        added_bytes += added.utf8_bytes
        messages.append(ConversationMessage("assistant", raw))
        if resolution.added_evidence:
            context_reply = "CAM CONTEXT RESPONSE\n" + "\n".join(
                resolution.added_evidence
            )
        else:
            context_reply = (
                "CAM CONTEXT RESPONSE\n"
                "No additional bounded CAM evidence matched that request."
            )
        messages.append(ConversationMessage("user", context_reply))

    call_tuple = tuple(calls)
    return NaturalExperimentReport(
        action=action,
        initial_context=_metrics(surfaced_initial),
        provider_calls=len(call_tuple),
        expansion_rounds=expansion_rounds,
        calls=call_tuple,
        context_requests=tuple(requests),
        final_conclusion=final_conclusion,
        conclusion_supported=conclusion_supported,
        total_input_tokens=_sum_optional(tuple(call.input_tokens for call in call_tuple)),
        total_output_tokens=_sum_optional(tuple(call.output_tokens for call in call_tuple)),
        total_provider_latency_seconds=_sum_optional_float(
            tuple(call.provider_latency_seconds for call in call_tuple)
        ),
        total_wall_latency_seconds=_sum_optional_float(
            tuple(call.wall_latency_seconds for call in call_tuple)
        ),
    )
