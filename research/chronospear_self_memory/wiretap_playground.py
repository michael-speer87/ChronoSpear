from __future__ import annotations

from dataclasses import dataclass, field
import json
import os

from cam_protocol import (
    CHANNELS,
    ProtocolDecision,
    parse_protocol_response,
    render_control_surface,
    render_protocol_packet,
)
from live_quest import call_provider
from memory import MemoryPacket, MemorySession
from playground import (
    INITIAL_BUDGET,
    PlaygroundState,
    handle_memory_command,
    print_admitted,
    print_header,
    print_map,
    print_packet,
    print_surfaced,
)
from seed import build_memory


WIRETAP_SYSTEM_PROMPT = """You are the reasoning component talking to ChronoSpear CAM.
CAM is a memory-management system. CAM does not reason about the question for you.
You interpret the user's question, decide whether supplied memory is sufficient, and choose what memory to request next.
Use only supplied evidence. Respect evidence-state labels exactly:
LOCKED=current architecture, EXPERIMENTALLY_PROVEN=test evidence, HYPOTHESIS=not locked,
PARKED=deferred, REJECTED=historical only, UNRESOLVED=open question.
Never upgrade a hypothesis into a decision.

You have ONLY this CAM control vocabulary. Output exactly ONE action per response:

ACTIVATE <exact concept name or alias>
  Use ONLY for a concept that is not currently surfaced.
  Every concept listed in the CAM CONTROL SURFACE is already surfaced.
  NEVER ACTIVATE a concept listed there.

EXPAND <surfaced concept> DESCRIPTION
EXPAND <surfaced concept> ASSOCIATIONS
EXPAND <surfaced concept> HISTORY
  Use ONLY a command explicitly listed under 'Valid EXPAND commands right now'.

If the supplied memory is sufficient, output exactly:
ANSWER: <concise answer>
EVIDENCE: <comma-separated evidence IDs, or none if the answer uses synopsis/description only>

Do not request memory in ordinary language. Do not invent new CAM verbs, channels, filters, or semantic queries.
CAM requests are memory operations, never statements about why the evidence is relevant.
"""


HELP = """Wiretap commands:
  send                                  Send the pending CAM delta to the LLM.
  response                              Reprint the most recent raw LLM response.
  conversation                          Show the complete LLM message transcript.
  packet                                Reprint the pending/current CAM delta and control surface.
  map                                   Show the current CAM memory availability map.
  surfaced                              List surfaced concepts.
  admitted                              Show evidence already admitted by CAM.
  activate <exact concept>              YOU execute exact activation.
  expand <concept> DESCRIPTION          YOU request only the Description channel.
  expand <concept> ASSOCIATIONS         YOU request the next Association page.
  expand <concept> HISTORY              YOU request the next History page.
  protocol                              Reprint the LLM -> CAM vocabulary.
  memory ...                            Use the mutable memory controls from playground.py.
  new                                   Start a fresh question while keeping memory edits.
  help                                  Show this help.
  quit                                  Exit.

Conversation rules:
  1. CAM builds and displays a packet/delta plus deterministic control surface.
  2. You inspect it.
  3. 'send' is the only command that calls the LLM.
  4. The raw LLM response is parsed but NEVER executed automatically.
  5. You decide whether to perform the requested ACTIVATE/EXPAND operation.
  6. A CAM operation creates a new pending delta. Run 'send' again when you choose.
"""


PROTOCOL_HELP = """LLM -> CAM protocol:
  ACTIVATE <exact concept name or alias>
  EXPAND <surfaced concept> DESCRIPTION
  EXPAND <surfaced concept> ASSOCIATIONS
  EXPAND <surfaced concept> HISTORY
  ANSWER: <answer>
  EVIDENCE: <ids or none>

Every concept shown in the CAM CONTROL SURFACE is already surfaced.
ACTIVATE may only name a concept not shown there.
Use only EXPAND commands explicitly listed by the current control surface.
CAM does not interpret ordinary-language memory requests in wiretap mode.
"""


@dataclass
class WiretapState:
    playground: PlaygroundState
    messages: list[dict[str, str]] = field(default_factory=list)
    pending_packet: MemoryPacket | None = None
    last_response: str | None = None
    last_usage: dict[str, object] = field(default_factory=dict)
    last_decision: ProtocolDecision | None = None


def provider_label() -> str:
    provider = os.environ.get("CS_DESIGN_PROVIDER", "groq").casefold()
    if provider == "groq":
        return f"groq / {os.environ.get('GROQ_MODEL', '<GROQ_MODEL not set>')}"
    if provider == "ollama":
        return f"ollama / {os.environ.get('OLLAMA_MODEL', 'qwen2.5-coder:7b')}"
    return provider


def print_protocol_view(packet: MemoryPacket, *, label: str) -> None:
    print_packet(packet, label=label)
    print_header("CAM CONTROL SURFACE")
    print(render_control_surface(packet))


def build_initial_state(memory) -> WiretapState | None:
    while True:
        print("\nAsk CAM a question. Packet #1 will be displayed but NOT sent automatically.")
        question = input("question> ").strip()
        if not question:
            continue
        if question.casefold() in {"quit", "exit"}:
            return None

        session = MemorySession()
        try:
            packet = memory.build_initial_packet(question, session, INITIAL_BUDGET)
        except (KeyError, ValueError) as exc:
            print(f"CAM could not build Packet #1: {exc}")
            continue

        playground = PlaygroundState(
            memory=memory,
            session=session,
            question=question,
            last_packet=packet,
            total_estimated_tokens=packet.estimated_tokens,
        )
        state = WiretapState(
            playground=playground,
            messages=[{"role": "system", "content": WIRETAP_SYSTEM_PROMPT}],
            pending_packet=packet,
        )
        print_protocol_view(packet, label="WIRETAP PACKET #1: INSPECT BEFORE SEND")
        print("\nNothing has been sent to the LLM yet. Type 'send' when you want to transmit this packet.")
        return state


def packet_has_memory(packet: MemoryPacket) -> bool:
    return bool(
        packet.new_synopses
        or packet.full_descriptions
        or packet.associations
        or packet.history
    )


def queue_packet(state: WiretapState, packet: MemoryPacket, label: str) -> None:
    state.playground.last_packet = packet
    state.pending_packet = packet
    state.playground.total_estimated_tokens += packet.estimated_tokens
    print_protocol_view(packet, label=label)
    print("\nThis CAM delta is pending. Inspect it, then type 'send' when you choose.")


def print_parsed_decision(decision: ProtocolDecision) -> None:
    print("\nPARSED ONLY, NOT EXECUTED:")
    print(f"  kind: {decision.kind}")
    if decision.concept is not None:
        print(f"  concept: {decision.concept}")
    if decision.channel is not None:
        print(f"  channel: {decision.channel}")
    if decision.answer is not None:
        print(f"  answer: {decision.answer}")
    if decision.evidence_ids:
        print(f"  evidence IDs: {', '.join(decision.evidence_ids)}")
    if decision.kind in {"activate", "expand"}:
        print("\nThe LLM requested a CAM operation. YOU must decide whether to execute it.")


def send_pending(state: WiretapState) -> None:
    if state.pending_packet is None:
        print("No new CAM delta is pending. Perform an activation/expansion first, or inspect the last response.")
        return

    packet = state.pending_packet
    state.messages.append({"role": "user", "content": render_protocol_packet(packet)})

    print_header("HUMAN GATE: SENDING PENDING CAM DELTA TO LLM")
    print(f"Provider: {provider_label()}")
    print(f"CAM delta estimate: {packet.estimated_tokens} tokens")

    try:
        result = call_provider(state.messages)
    except RuntimeError as exc:
        state.messages.pop()
        print(f"LLM call failed: {exc}")
        print("The CAM delta remains pending and may be sent again after fixing the provider issue.")
        return

    state.pending_packet = None
    state.last_response = result.text
    state.last_usage = result.usage
    state.messages.append({"role": "assistant", "content": result.text})

    print_header("RAW LLM RESPONSE: INSPECT BEFORE DOING ANYTHING")
    print(result.text)
    print(f"\nPROVIDER USAGE: {json.dumps(result.usage, sort_keys=True)}")

    try:
        decision = parse_protocol_response(result.text)
    except ValueError as exc:
        state.last_decision = None
        print(f"\nPROTOCOL VIOLATION: {exc}")
        print("No CAM action is taken. The model wandered outside the allowed vocabulary.")
        return

    state.last_decision = decision
    print_parsed_decision(decision)


def parse_manual_expand(argument: str) -> tuple[str, str]:
    body = argument.strip()
    parts = body.rsplit(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Usage: expand <surfaced concept> DESCRIPTION|ASSOCIATIONS|HISTORY")
    concept, channel = parts[0].strip(), parts[1].upper()
    if not concept:
        raise ValueError("expand requires a surfaced concept")
    if channel not in CHANNELS:
        raise ValueError(f"channel must be {'|'.join(CHANNELS)}")
    return concept, channel


def expand_manual(state: WiretapState, argument: str) -> None:
    if state.pending_packet is not None:
        print("A CAM delta is already pending. Send or inspect it before creating another delta.")
        return

    try:
        requested, channel = parse_manual_expand(argument)
    except ValueError as exc:
        print(exc)
        return

    canonical = state.playground.memory.resolve_surfaced_request(requested, state.playground.session)
    if canonical is None:
        print(f"'{requested}' does not name a currently surfaced concept.")
        print("Use 'activate <exact concept>' for a stored concept that has not been surfaced yet.")
        return

    try:
        packet = state.playground.memory.expand_channel(
            canonical,
            channel,
            state.playground.session,
            page_size=1,
        )
    except (KeyError, ValueError) as exc:
        print(f"CAM expansion failed: {exc}")
        return

    state.playground.expansion_count += 1
    if not packet_has_memory(packet):
        state.playground.last_packet = packet
        print_header(f"EXPAND {canonical} {channel}")
        print("No new memory remains in this channel.")
        print_map(packet)
        return

    queue_packet(
        state,
        packet,
        f"HUMAN-EXECUTED: EXPAND {canonical} {channel}",
    )


def activate_manual(state: WiretapState, requested: str) -> None:
    if state.pending_packet is not None:
        print("A CAM delta is already pending. Send or inspect it before creating another delta.")
        return

    requested = requested.strip()
    if not requested:
        print("Usage: activate <exact stored concept or alias>")
        return

    memory = state.playground.memory
    session = state.playground.session
    try:
        canonical = memory._resolve_name(requested)
    except KeyError:
        print(f"CAM exact activation failed: no stored concept/alias matches {requested!r}.")
        print("No fuzzy matching or correction was attempted.")
        return

    if canonical in session.surfaced_concepts:
        print(f"{canonical} is already surfaced. Use an EXPAND channel if you want more memory.")
        return

    session.surfaced_concepts.add(canonical)
    packet = memory._packet("ACTIVATION", (canonical,), session, INITIAL_BUDGET, include_description=False)
    queue_packet(state, packet, f"HUMAN-EXECUTED: ACTIVATE {canonical}")


def print_conversation(state: WiretapState) -> None:
    print_header("LLM MESSAGE TRANSCRIPT")
    for index, message in enumerate(state.messages, start=1):
        print(f"\n--- {index}. {message['role'].upper()} ---")
        print(message["content"])
    if state.pending_packet is not None:
        print("\n--- PENDING CAM DELTA (NOT YET SENT) ---")
        print(render_protocol_packet(state.pending_packet))


def print_last_response(state: WiretapState) -> None:
    print_header("MOST RECENT RAW LLM RESPONSE")
    if state.last_response is None:
        print("No LLM response yet.")
        return
    print(state.last_response)
    print(f"\nPROVIDER USAGE: {json.dumps(state.last_usage, sort_keys=True)}")
    if state.last_decision is not None:
        print_parsed_decision(state.last_decision)


def run_wiretap(state: WiretapState) -> str:
    print("\nYou are the interceptor. The LLM cannot execute CAM operations in this mode.")
    while True:
        raw = input("wiretap> ").strip()
        if not raw:
            continue

        command, _, argument = raw.partition(" ")
        command = command.casefold()

        if command in {"quit", "exit"}:
            return "quit"
        if command == "new":
            return "new"
        if command == "help":
            print(HELP)
        elif command == "protocol":
            print(PROTOCOL_HELP)
        elif command == "send":
            send_pending(state)
        elif command == "response":
            print_last_response(state)
        elif command == "conversation":
            print_conversation(state)
        elif command == "packet":
            label = "PENDING CAM DELTA" if state.pending_packet is not None else "MOST RECENT CAM DELTA"
            packet = state.pending_packet or state.playground.last_packet
            print_protocol_view(packet, label=label)
        elif command == "map":
            print_map(state.playground.last_packet)
        elif command == "surfaced":
            print_surfaced(state.playground)
        elif command == "admitted":
            print_admitted(state.playground)
        elif command == "expand":
            expand_manual(state, argument)
        elif command == "activate":
            activate_manual(state, argument)
        elif command == "memory":
            result = handle_memory_command(state.playground, argument)
            if result == "reset":
                return "reset"
        else:
            print("Unknown command. Type 'help' for the command list.")


def main() -> None:
    print_header("CHRONOSPEAR CAM ↔ LLM WIRETAP PLAYGROUND")
    print("Human-intercepted conversation mode with a tiny LLM -> CAM command vocabulary.")
    print(f"Configured provider: {provider_label()}")
    print("CAM never calls the LLM by itself, and LLM requests never execute by themselves.")
    print("\n" + PROTOCOL_HELP)
    print(HELP)

    memory = build_memory()
    while True:
        state = build_initial_state(memory)
        if state is None:
            break
        action = run_wiretap(state)
        if action == "quit":
            break
        if action == "reset":
            memory = build_memory()
            print("\nMemory reset to the clean seed. Wiretap conversation discarded.")

    print("\nWiretap playground closed.")


if __name__ == "__main__":
    main()
