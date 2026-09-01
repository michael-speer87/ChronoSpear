from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

ResponseKind = Literal["expand", "conclusion"]


class ExperimentProtocolError(RuntimeError):
    """Raised when a provider violates the bounded experiment protocol."""


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    return normalized


def _validate_token_count(value: int | None, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer or None.")


@dataclass(frozen=True, slots=True)
class ContextMetrics:
    record_count: int
    characters: int
    utf8_bytes: int


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """A deterministic, already-filtered collection of rendered CAM evidence."""

    bundle_id: str
    records: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id", _required_text(self.bundle_id, "Bundle ID"))
        if not self.records:
            raise ValueError("EvidenceBundle must contain at least one record.")
        normalized = tuple(_required_text(record, "Evidence record") for record in self.records)
        object.__setattr__(self, "records", normalized)

    @property
    def metrics(self) -> ContextMetrics:
        return _context_metrics(self.records)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    action: str
    evidence: tuple[str, ...]
    call_number: int


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Provider-neutral response and usage reported by that provider."""

    kind: ResponseKind
    text: str = ""
    selectors: tuple[str, ...] = ()
    reason: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    provider_latency_seconds: float | None = None
    wall_latency_seconds: float | None = None

    def __post_init__(self) -> None:
        _validate_token_count(self.input_tokens, "Input token count")
        _validate_token_count(self.output_tokens, "Output token count")
        for latency, label in (
            (self.provider_latency_seconds, "Provider latency"),
            (self.wall_latency_seconds, "Wall latency"),
        ):
            if latency is not None and latency < 0:
                raise ValueError(f"{label} must be non-negative or None.")
        if self.kind == "conclusion":
            object.__setattr__(self, "text", _required_text(self.text, "Provider conclusion text"))
            if self.selectors or self.reason:
                raise ValueError("A conclusion response cannot contain an expansion request.")
        elif self.kind == "expand":
            if self.text:
                raise ValueError("An expansion response cannot contain conclusion text.")
            if not self.selectors:
                raise ValueError("An expansion response must request at least one selector.")
            normalized = tuple(
                _required_text(selector, "Expansion selector") for selector in self.selectors
            )
            object.__setattr__(self, "selectors", normalized)
            object.__setattr__(self, "reason", _required_text(self.reason, "Expansion reason"))
        else:
            raise ValueError(f"Unknown provider response kind: {self.kind!r}.")

    @classmethod
    def conclusion(
        cls,
        text: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> ProviderResponse:
        return cls(
            kind="conclusion",
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @classmethod
    def expansion(
        cls,
        selectors: tuple[str, ...],
        reason: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> ProviderResponse:
        return cls(
            kind="expand",
            selectors=selectors,
            reason=reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


Provider = Callable[[ProviderRequest], ProviderResponse]


@dataclass(frozen=True, slots=True)
class ExperimentLimits:
    max_expansion_rounds: int = 2
    max_selectors_per_request: int = 2
    max_added_records: int = 8
    max_added_utf8_bytes: int = 2_000
    max_conclusion_characters: int = 500

    def __post_init__(self) -> None:
        for name in (
            "max_expansion_rounds",
            "max_selectors_per_request",
            "max_added_records",
            "max_added_utf8_bytes",
            "max_conclusion_characters",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")


@dataclass(frozen=True, slots=True)
class ExpansionResolution:
    granted: tuple[str, ...]
    rejected: tuple[str, ...]
    added_records: tuple[str, ...]


class WhitelistExpansionResolver:
    """Resolves only exact, pre-filtered selectors supplied by the experiment."""

    __slots__ = ("_bundles",)

    def __init__(self, bundles: Mapping[str, EvidenceBundle]) -> None:
        self._bundles = dict(bundles)
        if len(self._bundles) != len(bundles):
            raise ValueError("Expansion selector names must be unique.")
        for selector in self._bundles:
            _required_text(selector, "Expansion selector")

    def resolve(
        self,
        selectors: tuple[str, ...],
        *,
        seen_records: frozenset[str],
        remaining_records: int,
        remaining_utf8_bytes: int,
        max_selectors: int,
    ) -> ExpansionResolution:
        granted: list[str] = []
        rejected: list[str] = []
        added: list[str] = []
        selected = selectors[:max_selectors]

        for selector in selectors[max_selectors:]:
            rejected.append(f"{selector}: selector limit exceeded")

        current_seen = set(seen_records)
        for selector in selected:
            bundle = self._bundles.get(selector)
            if bundle is None:
                rejected.append(f"{selector}: not whitelisted")
                continue
            novel = tuple(record for record in bundle.records if record not in current_seen)
            if not novel:
                rejected.append(f"{selector}: no new evidence")
                continue
            novel_bytes = _context_metrics(novel).utf8_bytes
            if len(novel) > remaining_records or novel_bytes > remaining_utf8_bytes:
                rejected.append(f"{selector}: evidence budget exceeded")
                continue
            granted.append(selector)
            added.extend(novel)
            current_seen.update(novel)
            remaining_records -= len(novel)
            remaining_utf8_bytes -= novel_bytes

        return ExpansionResolution(tuple(granted), tuple(rejected), tuple(added))


@dataclass(frozen=True, slots=True)
class ExpansionRequestRecord:
    call_number: int
    selectors: tuple[str, ...]
    reason: str
    granted: tuple[str, ...]
    rejected: tuple[str, ...]
    added_context: ContextMetrics


@dataclass(frozen=True, slots=True)
class ProviderCallRecord:
    call_number: int
    context: ContextMetrics
    input_tokens: int | None
    output_tokens: int | None
    response_kind: ResponseKind
    model: str | None
    provider_latency_seconds: float | None
    wall_latency_seconds: float | None


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    action: str
    initial_context: ContextMetrics
    expansion_requests: tuple[ExpansionRequestRecord, ...]
    provider_calls: int
    calls: tuple[ProviderCallRecord, ...]
    total_input_tokens: int | None
    total_output_tokens: int | None
    final_conclusion: str


def _context_metrics(records: tuple[str, ...]) -> ContextMetrics:
    rendered = "\n".join(records)
    return ContextMetrics(len(records), len(rendered), len(rendered.encode("utf-8")))


def _total_usage(
    calls: tuple[ProviderCallRecord, ...], *, input_tokens: bool
) -> int | None:
    values = tuple(
        call.input_tokens if input_tokens else call.output_tokens for call in calls
    )
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def run_action_experiment(
    action: str,
    initial_evidence: EvidenceBundle,
    resolver: WhitelistExpansionResolver,
    provider: Provider,
    limits: ExperimentLimits | None = None,
) -> ExperimentReport:
    """Run one non-persistent action with bounded, whitelist-only expansion."""

    normalized_action = _required_text(action, "Action")
    active_limits = limits or ExperimentLimits()
    evidence = list(initial_evidence.records)
    seen_records = set(evidence)
    expansion_records: list[ExpansionRequestRecord] = []
    call_records: list[ProviderCallRecord] = []
    added_record_count = 0
    added_byte_count = 0
    expansion_rounds = 0

    while True:
        call_number = len(call_records) + 1
        response = provider(
            ProviderRequest(normalized_action, tuple(evidence), call_number)
        )
        call_records.append(
            ProviderCallRecord(
                call_number,
                _context_metrics(tuple(evidence)),
                response.input_tokens,
                response.output_tokens,
                response.kind,
                response.model,
                response.provider_latency_seconds,
                response.wall_latency_seconds,
            )
        )

        if response.kind == "conclusion":
            if len(response.text) > active_limits.max_conclusion_characters:
                raise ExperimentProtocolError("Provider conclusion exceeds the compactness limit.")
            calls = tuple(call_records)
            return ExperimentReport(
                action=normalized_action,
                initial_context=initial_evidence.metrics,
                expansion_requests=tuple(expansion_records),
                provider_calls=len(calls),
                calls=calls,
                total_input_tokens=_total_usage(calls, input_tokens=True),
                total_output_tokens=_total_usage(calls, input_tokens=False),
                final_conclusion=response.text,
            )

        if expansion_rounds >= active_limits.max_expansion_rounds:
            raise ExperimentProtocolError(
                "Provider requested expansion after the expansion round limit."
            )
        expansion_rounds += 1
        resolution = resolver.resolve(
            response.selectors,
            seen_records=frozenset(seen_records),
            remaining_records=active_limits.max_added_records - added_record_count,
            remaining_utf8_bytes=active_limits.max_added_utf8_bytes - added_byte_count,
            max_selectors=active_limits.max_selectors_per_request,
        )
        metrics = _context_metrics(resolution.added_records)
        expansion_records.append(
            ExpansionRequestRecord(
                call_number=call_number,
                selectors=response.selectors,
                reason=response.reason,
                granted=resolution.granted,
                rejected=resolution.rejected,
                added_context=metrics,
            )
        )
        evidence.extend(resolution.added_records)
        seen_records.update(resolution.added_records)
        added_record_count += metrics.record_count
        added_byte_count += metrics.utf8_bytes
