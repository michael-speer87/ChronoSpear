from __future__ import annotations

from dataclasses import dataclass, field
import json
import os

from live_quest import SYSTEM_PROMPT, call_provider, parse_decision
from memory import MemoryPacket, MemorySession
from playground import (
    EXPANSION_BUDGET,
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


HELP = """Wiretap commands:
  send                        Send the pending CAM delta to the LLM. Nothing is auto-executed.
  response                    Reprint the most recent raw LLM response.
  conversation                Show the complete LLM message transcript so far.
  packet                      Reprint the pending/current CAM delta.
  map                         Show the current CAM memory availability map.
  surfaced                    List surfaced concepts.
  admitted                    Show evidence already admitted by CAM this session.
  expand <concept>            YOU execute a bounded expansion of a surfaced concept.
  activate <exact concept>    YOU explicitly surface a stored concept by exact name/alias.
  memory ...                  Use the same mutable memory controls as playground.py.
  new                         Start a fresh question while keeping memory edits.
  help                        Show this help.
  quit                        Exit.

Conversation rules:
  1. CAM builds and displays a packet/delta.
  2. You inspect it.
  3. 'send' is the only command that calls the LLM.
  4. The raw LLM response is displayed but NEVER executed automatically.
  5. You decide whether to expand/activate memory, ignore the request, or do something else.
  6. A CAM action creates a new pending delta. Run 'send' again when you choose.
"""


@dataclass
class WiretapState:
    playground: PlaygroundState
    messages: list[dict[str, str]] = field(default_factory=list)
    pending_packet: MemoryPacket | None = None
    last_response: str | None = None
    last_usage: dict[str, object] = field(default_factory=dict)


def provider_label() -> str:
    provider = os.environ.get("CS_DESIGN_PROVIDER", "groq").casefold()
    if provider == "groq":
        return f"groq / {os.environ.get('GROQ_MODEL', '<GROQ_MODEL not set>')}"
    if provider == "ollama":
        return f"ollama / {os.environ.get('OLLAMA_MODEL', 'qwen2.5-coder:7b')}"
    return provider


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
            messages=[{"role": "system", "content": SYSTEM_PROMPT}],
            pending_packet=packet,
        )
        print_packet(packet, label="WIRETAP PACKET #1: INSPECT BEFORE SEND")
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
    print_packet(packet, label=label)
    print("\nThis CAM delta is pending. Inspect it, then type 'send' when you choose.")


def send_pending(state: WiretapState) -> None:
    if state.pending_packet is None:
        print("No new CAM delta is pending. Perform an expansion/activation first, or inspect the last response.")
        return

    packet = state.pending_packet
    state.messages.append({"role": "user", "content": packet.render()})

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
        decision = parse_decision(result.text)
    except ValueError as exc:
        print(f"\nPARSE NOTE: response did not follow the research protocol exactly: {exc}")
        print("No action is taken. You decide what to do next.")
        return

    print("\nPARSED ONLY, NOT EXECUTED:")
    print(f"  kind: {decision.kind}")
    print(f"  text: {decision.text}")
    if decision.evidence_ids:
        print(f"  evidence IDs: {', '.join(decision.evidence_ids)}")
    if decision.kind == "request_more":
        print("\nThe LLM requested more memory. YOU must decide whether/how to satisfy it.")


def expand_manual(state: WiretapState, requested: str) -> None:
    if state.pending_packet is not None:
        print("A CAM delta is already pending. Send or inspect it before creating another delta.")
        return

    requested = requested.strip()
    if not requested:
        print("Usage: expand <surfaced concept>")
        return

    canonical = state.playground.memory.resolve_surfaced_request(requested, state.playground.session)
    if canonical is None:
        print(f"'{requested}' does not name a currently surfaced concept.")
        print("Use 'activate <exact concept>' for a stored concept that has not been surfaced yet.")
        return

    try:
        packet = state.playground.memory.expand(canonical, state.playground.session, EXPANSION_BUDGET)
    except (KeyError, ValueError) as exc:
        print(f"CAM expansion failed: {exc}")
        return

    state.playground.expansion_count += 1
    if not packet_has_memory(packet):
        state.playground.last_packet = packet
        print_header(f"EXPANSION: {canonical}")
        print("No new evidence remains for this bounded path.")
        print_map(packet)
        return

    queue_packet(state, packet, f"HUMAN-EXECUTED EXPANSION {state.playground.expansion_count}: {canonical}")


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
        print(f"{canonical} is already surfaced. Use 'expand {canonical}' if you want more memory.")
        return

    session.surfaced_concepts.add(canonical)
    # Research-only harness: use the same internal packet builder as initial activation,
    # but with a zero evidence budget so activation itself stays synopsis-only.
    packet = memory._packet("ACTIVATION", (canonical,), session, INITIAL_BUDGET, include_description=False)
    queue_packet(state, packet, f"HUMAN-EXECUTED EXACT ACTIVATION: {canonical}")


def print_conversation(state: WiretapState) -> None:
    print_header("LLM MESSAGE TRANSCRIPT")
    for index, message in enumerate(state.messages, start=1):
        print(f"\n--- {index}. {message['role'].upper()} ---")
        print(message["content"])
    if state.pending_packet is not None:
        print("\n--- PENDING CAM DELTA (NOT YET SENT) ---")
        print(state.pending_packet.render())


def print_last_response(state: WiretapState) -> None:
    print_header("MOST RECENT RAW LLM RESPONSE")
    if state.last_response is None:
        print("No LLM response yet.")
        return
    print(state.last_response)
    print(f"\nPROVIDER USAGE: {json.dumps(state.last_usage, sort_keys=True)}")


def run_wiretap(state: WiretapState) -> str:
    print("\nYou are the interceptor. The LLM cannot execute CAM actions in this mode.")
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
        elif command == "send":
            send_pending(state)
        elif command == "response":
            print_last_response(state)
        elif command == "conversation":
            print_conversation(state)
        elif command == "packet":
            label = "PENDING CAM DELTA" if state.pending_packet is not None else "MOST RECENT CAM DELTA"
            packet = state.pending_packet or state.playground.last_packet
            print_packet(packet, label=label)
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
    print("Human-intercepted conversation mode.")
    print(f"Configured provider: {provider_label()}")
    print("CAM never calls the LLM by itself, and LLM requests never execute by themselves.")
    print("\n" + HELP)

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
