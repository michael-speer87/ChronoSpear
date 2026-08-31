from __future__ import annotations

from dataclasses import dataclass


CHANNELS = ("DESCRIPTION", "ASSOCIATIONS", "HISTORY")


@dataclass(frozen=True)
class ProtocolDecision:
    kind: str
    concept: str | None = None
    channel: str | None = None
    answer: str | None = None
    evidence_ids: tuple[str, ...] = ()


def parse_protocol_response(text: str) -> ProtocolDecision:
    """Parse the deliberately tiny LLM -> CAM control vocabulary."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty model response")

    first = lines[0]
    upper = first.upper()

    if upper.startswith("ANSWER:"):
        answer = first.split(":", 1)[1].strip()
        if not answer:
            raise ValueError("ANSWER requires text")
        evidence_line = next((line for line in lines[1:] if line.upper().startswith("EVIDENCE:")), None)
        if evidence_line is None:
            raise ValueError("ANSWER requires an EVIDENCE line")
        raw_ids = evidence_line.split(":", 1)[1].strip()
        evidence_ids = tuple(value.strip() for value in raw_ids.split(",") if value.strip())
        return ProtocolDecision("answer", answer=answer, evidence_ids=evidence_ids)

    if upper.startswith("ACTIVATE "):
        if len(lines) != 1:
            raise ValueError("ACTIVATE response must contain exactly one command line")
        concept = first[len("ACTIVATE ") :].strip()
        if not concept:
            raise ValueError("ACTIVATE requires an exact concept name or alias")
        return ProtocolDecision("activate", concept=concept)

    if upper.startswith("EXPAND "):
        if len(lines) != 1:
            raise ValueError("EXPAND response must contain exactly one command line")
        body = first[len("EXPAND ") :].strip()
        parts = body.rsplit(maxsplit=1)
        if len(parts) != 2:
            raise ValueError("EXPAND requires: EXPAND <concept> DESCRIPTION|ASSOCIATIONS|HISTORY")
        concept, channel = parts[0].strip(), parts[1].upper()
        if not concept:
            raise ValueError("EXPAND requires a concept name")
        if channel not in CHANNELS:
            allowed = "|".join(CHANNELS)
            raise ValueError(f"unknown CAM channel {channel!r}; expected {allowed}")
        return ProtocolDecision("expand", concept=concept, channel=channel)

    raise ValueError(
        "response is outside CAM protocol; expected ACTIVATE <concept>, "
        "EXPAND <concept> DESCRIPTION|ASSOCIATIONS|HISTORY, or ANSWER: ..."
    )
