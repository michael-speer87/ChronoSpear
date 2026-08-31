from __future__ import annotations

from dataclasses import dataclass

from memory import DesignMemory, EvidenceState, MemoryPacket, MemorySession, PacketBudget
from memory_interface import MemoryInterface
from seed import build_memory


HELP = """Commands:
  expand <concept>              Reveal the next bounded CAM delta for a surfaced concept.
  map                           Show the current memory availability map.
  surfaced                      List concepts currently surfaced in this reasoning session.
  admitted                      Show evidence IDs already admitted to this session.
  packet                        Reprint the most recent packet/delta.
  memory                        Show memory-interface commands.
  memory summary                Count current Concepts, Associations, and Occurrences.
  memory concepts               List all stored Concepts.
  memory associations           List all stored Associations.
  memory history                List all stored Historical Occurrences.
  memory show <concept>         Show one Concept's synopsis, description, and aliases.
  memory add concept            Interactively add a Concept.
  memory add association        Interactively add an Association.
  memory add occurrence         Interactively add a Historical Occurrence.
  memory remove concept <name>  Remove only the Concept. References are NOT cascaded.
  memory remove association <id>
  memory remove occurrence <id>
  memory integrity              Report dangling references caused by destructive edits.
  memory reset                  Discard all playground edits and reload the clean seed.
  new                           Start a new question while keeping playground memory edits.
  help                          Show these commands.
  quit                          Exit the playground.

Notes:
  - Packet #1 is intentionally synopsis-only. It exposes the memory map but no
    Associations or Historical Occurrences.
  - Each expansion reveals at most one new Association and one new Historical
    Occurrence for the named surfaced concept, plus its full Description if it
    has not already been supplied.
  - Expansion packets are deltas. Previously admitted evidence is not sent again.
  - Memory edits are in-memory only. seed.py is never changed by playground commands.
  - Concept removal is intentionally non-cascading so broken references remain visible.
"""


MEMORY_HELP = """Memory interface:
  memory summary
  memory concepts
  memory associations
  memory history
  memory show <concept>
  memory add concept
  memory add association
  memory add occurrence
  memory remove concept <name>      NON-CASCADING: references remain on purpose.
  memory remove association <id>
  memory remove occurrence <id>
  memory integrity
  memory reset

All edits exist only for this playground process. Use 'new' after editing if you
want a fresh reasoning session against the mutated memory.
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
        marker = "" if name in state.memory.concepts else " [MISSING FROM CURRENT MEMORY]"
        print(f"- {name}{marker}")


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
        print("The question must explicitly mention at least one currently stored concept or alias.")
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
            print("Use a current Concept name, or inspect the store with 'memory concepts' after starting another session.")
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

    try:
        packet = state.memory.expand(canonical, state.session, EXPANSION_BUDGET)
    except (KeyError, ValueError) as exc:
        print_header(f"EXPANSION FAILED: {canonical}")
        print(f"CAM could not expand this path: {exc}")
        print("Run 'memory integrity' if you have been destructively editing memory.")
        return

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


def parse_state(raw: str) -> EvidenceState:
    normalized = raw.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "proven": EvidenceState.PROVEN,
        "experimentally_proven": EvidenceState.PROVEN,
        "locked": EvidenceState.LOCKED,
        "hypothesis": EvidenceState.HYPOTHESIS,
        "parked": EvidenceState.PARKED,
        "rejected": EvidenceState.REJECTED,
        "unresolved": EvidenceState.UNRESOLVED,
    }
    if normalized not in aliases:
        allowed = ", ".join(aliases)
        raise ValueError(f"unknown evidence state {raw!r}; use one of: {allowed}")
    return aliases[normalized]


def prompt_csv(label: str) -> tuple[str, ...]:
    raw = input(f"{label}> ").strip()
    return tuple(value.strip() for value in raw.split(",") if value.strip())


def memory_summary(interface: MemoryInterface) -> None:
    print_header("MEMORY STORE SUMMARY")
    print(f"Concepts: {len(interface.memory.concepts)}")
    print(f"Associations: {len(interface.memory.associations)}")
    print(f"Historical Occurrences: {len(interface.memory.occurrences)}")


def memory_list_concepts(interface: MemoryInterface) -> None:
    print_header("MEMORY STORE: CONCEPTS")
    for concept in sorted(interface.memory.concepts.values(), key=lambda item: item.name.casefold()):
        aliases = ", ".join(concept.aliases) if concept.aliases else "none"
        print(f"- {concept.name} | synopsis={concept.synopsis!r} | aliases={aliases}")


def memory_list_associations(interface: MemoryInterface) -> None:
    print_header("MEMORY STORE: ASSOCIATIONS")
    if not interface.memory.associations:
        print("- none")
        return
    for association in interface.memory.associations:
        provenance = ", ".join(association.provenance) if association.provenance else "none"
        print(f"- {association.render()} | provenance={provenance}")


def memory_list_history(interface: MemoryInterface) -> None:
    print_header("MEMORY STORE: HISTORICAL OCCURRENCES")
    if not interface.memory.occurrences:
        print("- none")
        return
    for occurrence in interface.memory.occurrences:
        participants = ", ".join(occurrence.participants) if occurrence.participants else "none"
        print(f"- {occurrence.render()} | participants={participants}")


def memory_show_concept(interface: MemoryInterface, requested: str) -> None:
    requested = requested.strip()
    if not requested:
        print("Usage: memory show <concept>")
        return
    key = requested.casefold()
    canonical = interface.memory._aliases.get(key)
    if canonical is None or canonical not in interface.memory.concepts:
        print(f"Concept not found: {requested}")
        return
    concept = interface.memory.concepts[canonical]
    print_header(f"MEMORY CONCEPT: {concept.name}")
    print(f"Synopsis: {concept.synopsis}")
    print(f"Description: {concept.description}")
    print(f"Aliases: {', '.join(concept.aliases) if concept.aliases else 'none'}")


def memory_add_concept(interface: MemoryInterface) -> None:
    print_header("ADD CONCEPT")
    print("Adds data only to this running playground.")
    name = input("name> ").strip()
    synopsis = input("synopsis> ").strip()
    description = input("description> ").strip()
    aliases = prompt_csv("aliases (comma-separated, blank for none)")
    try:
        interface.add_concept(name, synopsis, description, aliases)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Concept: {name}")


def memory_add_association(interface: MemoryInterface) -> None:
    print_header("ADD ASSOCIATION")
    print("CAM does not infer semantics here. The fields are stored exactly as entered.")
    evidence_id = input("evidence id> ").strip()
    source = input("source> ").strip()
    relationship = input("relationship> ").strip()
    target = input("target> ").strip()
    raw_state = input("state [locked/proven/hypothesis/parked/rejected/unresolved]> ").strip()
    provenance = prompt_csv("provenance IDs (comma-separated, blank for none)")
    try:
        state = parse_state(raw_state)
        interface.add_association(evidence_id, source, relationship, target, state, provenance)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Association: {evidence_id}")


def memory_add_occurrence(interface: MemoryInterface) -> None:
    print_header("ADD HISTORICAL OCCURRENCE")
    evidence_id = input("evidence id> ").strip()
    date = input("date/text coordinate> ").strip()
    participants = prompt_csv("participants (comma-separated)")
    story = input("story> ").strip()
    raw_state = input("state [locked/proven/hypothesis/parked/rejected/unresolved]> ").strip()
    try:
        state = parse_state(raw_state)
        interface.add_occurrence(evidence_id, date, participants, story, state)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Historical Occurrence: {evidence_id}")


def memory_integrity(interface: MemoryInterface) -> None:
    report = interface.integrity_report()
    print_header("MEMORY INTEGRITY")
    if report.clean:
        print("No dangling Concept references detected.")
        return

    print("Dangling Association sources:")
    print("  " + (", ".join(report.dangling_association_sources) or "none"))
    print("Dangling Association targets:")
    print("  " + (", ".join(report.dangling_association_targets) or "none"))
    print("Dangling Historical Occurrence participants:")
    print("  " + (", ".join(report.dangling_occurrence_participants) or "none"))


def handle_memory_command(state: PlaygroundState, argument: str) -> str | None:
    interface = MemoryInterface(state.memory)
    raw = argument.strip()
    if not raw:
        print(MEMORY_HELP)
        return None

    action, _, remainder = raw.partition(" ")
    action = action.casefold()
    remainder = remainder.strip()

    if action == "summary":
        memory_summary(interface)
    elif action == "concepts":
        memory_list_concepts(interface)
    elif action == "associations":
        memory_list_associations(interface)
    elif action in {"history", "occurrences"}:
        memory_list_history(interface)
    elif action == "show":
        memory_show_concept(interface, remainder)
    elif action == "integrity":
        memory_integrity(interface)
    elif action == "reset":
        return "reset"
    elif action == "add":
        kind, _, _ = remainder.partition(" ")
        kind = kind.casefold()
        if kind == "concept":
            memory_add_concept(interface)
        elif kind == "association":
            memory_add_association(interface)
        elif kind in {"occurrence", "history"}:
            memory_add_occurrence(interface)
        else:
            print("Usage: memory add concept|association|occurrence")
    elif action == "remove":
        kind, _, target = remainder.partition(" ")
        kind = kind.casefold()
        target = target.strip()
        if not target:
            print("Usage: memory remove concept <name> | association <id> | occurrence <id>")
            return None
        try:
            if kind == "concept":
                removed = interface.remove_concept(target)
                print(f"Removed Concept only: {removed.name}")
                print("References were intentionally NOT cascaded. Run 'memory integrity'.")
            elif kind == "association":
                removed = interface.remove_association(target)
                print(f"Removed Association: {removed.id}")
            elif kind in {"occurrence", "history"}:
                removed = interface.remove_occurrence(target)
                print(f"Removed Historical Occurrence: {removed.id}")
            else:
                print("Usage: memory remove concept|association|occurrence <name-or-id>")
        except KeyError:
            print(f"Nothing removed; not found: {target}")
    else:
        print(MEMORY_HELP)
    return None


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
        elif command == "memory":
            result = handle_memory_command(state, argument)
            if result == "reset":
                return "reset"
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
        if action == "reset":
            memory = build_memory()
            print("\nMemory reset to the clean seed. Current reasoning session discarded.")

    print("\nPlayground closed.")


if __name__ == "__main__":
    main()
