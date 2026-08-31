from __future__ import annotations

from dataclasses import dataclass
import re

from memory import MemoryPacket


CHANNELS = ("DESCRIPTION", "ASSOCIATIONS", "HISTORY")
MAX_AND_COMMANDS = 4


@dataclass(frozen=True)
class ProtocolDecision:
    kind: str
    concept: str | None = None
    channel: str | None = None
    answer: str | None = None
    evidence_ids: tuple[str, ...] = ()
    operations: tuple["ProtocolDecision", ...] = ()


def _parse_memory_command(command: str) -> ProtocolDecision:
    command = command.strip()
    upper = command.upper()

    if upper.startswith("ACTIVATE "):
        concept = command[len("ACTIVATE ") :].strip()
        if not concept:
            raise ValueError("ACTIVATE requires an exact concept name or alias")
        return ProtocolDecision("activate", concept=concept)

    if upper.startswith("EXPAND "):
        body = command[len("EXPAND ") :].strip()
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
        "memory command is outside CAM protocol; expected ACTIVATE <concept> or "
        "EXPAND <concept> DESCRIPTION|ASSOCIATIONS|HISTORY"
    )


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

    if len(lines) != 1:
        raise ValueError(
            "memory requests must be one response line; join independent commands with AND"
        )

    # AND is only a separator when followed by another CAM memory verb. This avoids
    # breaking a future concept name that happens to contain the word 'and'.
    commands = re.split(
        r"\s+AND\s+(?=(?:ACTIVATE|EXPAND)\s)",
        first,
        flags=re.IGNORECASE,
    )
    if len(commands) > MAX_AND_COMMANDS:
        raise ValueError(f"AND chain exceeds maximum of {MAX_AND_COMMANDS} commands")

    operations = tuple(_parse_memory_command(command) for command in commands)
    if len(operations) == 1:
        return operations[0]
    return ProtocolDecision("batch", operations=operations)


def render_control_surface(packet: MemoryPacket) -> str:
    """Render valid state-aware CAM operations without inferring semantic relevance."""
    lines = [
        "CAM CONTROL SURFACE",
        "Every concept listed below is ALREADY SURFACED. NEVER ACTIVATE a listed concept.",
        "Use only EXPAND commands explicitly listed below, ACTIVATE an exact unsurfaced concept, or ANSWER.",
        "You may join up to 4 INDEPENDENT memory commands on one line using AND.",
        "Every command in an AND chain must already be valid against THIS control surface before any command executes.",
        "Do not ACTIVATE a concept and EXPAND that newly activated concept in the same AND chain.",
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
            "AND example:",
            "EXPAND Concept A DESCRIPTION AND EXPAND Concept B HISTORY",
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
