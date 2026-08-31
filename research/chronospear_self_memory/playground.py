from __future__ import annotations

from dataclasses import dataclass

from memory import DesignMemory, MemoryPacket, MemorySession, PacketBudget
from seed import build_memory


HELP = """Commands:
  expand <concept>   Reveal the next bounded CAM delta for a surfaced concept.
  map                Show the current memory availability map.
  surfaced           List concepts currently surfaced in this reasoning session.
  admitted           Show evidence IDs already admitted to this session.
  packet             Reprint the most recent packet/delta.
  new                Start a new question with a fresh reasoning session.
  help               Show these commands.
  quit               Exit the playground.

Notes:
  - Packet #1 is intentionally synopsis-only. It exposes the memory map but no
    Associations or Historical Occurrences.
  - Each expansion reveals at most one new Association and one new Historical
    Occurrence for the named surfaced concept, plus its full Description if it
    has not already been supplied.
  - Expansion packets are deltas. Previously admitted evidence is not sent again.
"""


INITIAL_BUDGET = PacketBudget(associations_per_concept=0, history_per_concept=0)
EXPANSION_BUDGET = PacketBudget(associations_per_concept=1, history_per_concept=1)


@dataclass
class PlaygroundState:
    memory: DesignMemory
    session: MemorySession
    question: str
    last_packet: MemoryPacket
    total_estimated_tokens: int
    expansion_count: int = 0


def print_header(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def print_packet(packet: MemoryPacket, *, label: str) -> None:
    print_header(label)
    print(packet.render())
    print(f"\nDELTA ESTIMATED TOKENS: {packet.estimated_tokens}")


def print_map(packet: MemoryPacket) -> None:
    print_header("MEMORY AVAILABILITY MAP")
    if not packet.memory_map:
        print("No surfaced concepts.")
        return
    for entry in packet.memory_map:
        print(entry.render())


def print_surfaced(state: PlaygroundState) -> None:
    print_header("SURFACED CONCEPTS")
    for name in sorted(state.session.surfaced_concepts):
        print(f"- {name}")


def print_admitted(state: PlaygroundState) -> None:
    print_header("ADMITTED EVIDENCE")
    print("Synopses:")
    for name in sorted(state.session.seen_synopses):
        print(f"  - {name}")
    print("Full descriptions:")
    if state.session.seen_descriptions:
        for name in sorted(state.session.seen_descriptions):
            print(f"  - {name}")
    else:
        print("  - none")
    print("Associations:")
    if state.session.seen_associations:
        for evidence_id in sorted(state.session.seen_associations):
            print(f"  - {evidence_id}")
    else:
        print("  - none")
    print("Historical occurrences:")
    if state.session.seen_history:
        for evidence_id in sorted(state.session.seen_history):
            print(f"  - {evidence_id}")
    else:
        print("  - none")
    print(f"\nCumulative CAM delta estimate: {state.total_estimated_tokens} tokens")
    print(f"Expansion count: {state.expansion_count}")


def start_question(memory: DesignMemory) -> PlaygroundState | None:
    while True:
        print("\nAsk ChronoSpear design CAM a question.")
        print("The question must explicitly mention at least one seeded concept.")
        question = input("question> ").strip()
        if not question:
            continue
        if question.casefold() in {"quit", "exit"}:
            return None

        session = MemorySession()
        try:
            packet = memory.build_initial_packet(question, session, INITIAL_BUDGET)
        except ValueError as exc:
            print(f"CAM could not activate a concept: {exc}")
            print("Try naming something such as Description, Expansion, Packet #1, MCP, CAM, or Language Surface.")
            continue

        state = PlaygroundState(
            memory=memory,
            session=session,
            question=question,
            last_packet=packet,
            total_estimated_tokens=packet.estimated_tokens,
        )
        print_packet(packet, label="PACKET #1: SYNOPSIS-ONLY START")
        return state


def expand_concept(state: PlaygroundState, requested: str) -> None:
    requested = requested.strip()
    if not requested:
        print("Usage: expand <surfaced concept>")
        return

    canonical = state.memory.resolve_surfaced_request(requested, state.session)
    if canonical is None:
        print(f"'{requested}' does not name a currently surfaced concept.")
        print("Use 'surfaced' or 'map' to see what CAM currently exposes.")
        return

    packet = state.memory.expand(canonical, state.session, EXPANSION_BUDGET)
    state.last_packet = packet
    state.total_estimated_tokens += packet.estimated_tokens
    state.expansion_count += 1

    empty = not (
        packet.new_synopses
        or packet.full_descriptions
        or packet.associations
        or packet.history
    )
    if empty:
        print_header(f"EXPANSION: {canonical}")
        print("No new evidence remains for this bounded expansion path.")
        print_map(packet)
        return

    print_packet(packet, label=f"EXPANSION {state.expansion_count}: {canonical}")


def run_session(state: PlaygroundState) -> str:
    print("\nType 'help' for commands. You are the reasoner; CAM only exposes memory.")
    while True:
        raw = input("cam> ").strip()
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
        elif command == "map":
            print_map(state.last_packet)
        elif command == "surfaced":
            print_surfaced(state)
        elif command == "admitted":
            print_admitted(state)
        elif command == "packet":
            print_packet(state.last_packet, label="MOST RECENT CAM DELTA")
        elif command == "expand":
            expand_concept(state, argument)
        else:
            print("Unknown command. Type 'help' for the command list.")


def main() -> None:
    print_header("CHRONOSPEAR SELF-MEMORY PLAYGROUND")
    print("Manual CAM exploration mode. No LLM is called.")
    print("Packet #1 starts shallow; you choose what memory to expand.")
    print("This is a research harness, not production CAM.")
    print("\n" + HELP)

    memory = build_memory()
    while True:
        state = start_question(memory)
        if state is None:
            break
        action = run_session(state)
        if action == "quit":
            break

    print("\nPlayground closed.")


if __name__ == "__main__":
    main()
