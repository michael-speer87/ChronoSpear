from __future__ import annotations

from dataclasses import dataclass

from memory import MemoryPacket


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


def render_control_surface(packet: MemoryPacket) -> str:
    """Render valid state-aware CAM operations without inferring semantic relevance."""
    lines = [
        "CAM CONTROL SURFACE",
        "Every concept listed below is ALREADY SURFACED. NEVER ACTIVATE a listed concept.",
        "Use only an EXPAND command explicitly listed below, or ANSWER if memory is sufficient.",
        "",
        "Currently surfaced concepts:",
    ]

    if packet.memory_map:
        lines.extend(f"- {entry.concept}" for entry in packet.memory_map)
    else:
        lines.append("- none")

    commands: list[str] = []
    for entry in packet.memory_map:
        if entry.description_remaining:
            commands.append(f"EXPAND {entry.concept} DESCRIPTION")
        if entry.associations_remaining > 0:
            commands.append(f"EXPAND {entry.concept} ASSOCIATIONS")
        if entry.history_remaining > 0:
            commands.append(f"EXPAND {entry.concept} HISTORY")

    lines.extend(["", "Valid EXPAND commands right now:"])
    if commands:
        lines.extend(f"- {command}" for command in commands)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "ACTIVATE rule:",
            "ACTIVATE may name only an exact stored concept or alias that is NOT currently surfaced above.",
            "Do not use ACTIVATE to refresh, reopen, or request more memory for an already surfaced concept.",
        ]
    )
    return "\n".join(lines)


def render_protocol_packet(packet: MemoryPacket) -> str:
    """Wrap a CAM memory delta with its deterministic current control surface."""
    return f"{packet.render()}\n\n{render_control_surface(packet)}"
