from __future__ import annotations

import argparse

import auto_handshake as handshake
import cam_native_handshake as native
from cam_native_dataset import CAM_NATIVE_SYSTEM_PROMPT
from llama_cpp_provider import LlamaCppCamNativeProvider
from memory import DesignMemory, EvidenceState
from memory_interface import MemoryInterface


HELP = """Mini-Igor world playground commands:
  help                                  Show this help.
  summary                               Count Concepts, Associations, and Historical Occurrences.
  concepts                              List stored Concepts.
  associations                          List stored Associations.
  history                               List stored Historical Occurrences.
  show <concept>                        Show one Concept's synopsis, description, and aliases.
  add concept                           Interactively add a Concept.
  add association                       Interactively add an Association.
  add occurrence                        Interactively add a Historical Occurrence.
  remove concept <name>                 Remove only the Concept; references are not cascaded.
  remove association <id>               Remove one Association.
  remove occurrence <id>                Remove one Historical Occurrence.
  integrity                             Report dangling Concept references.
  ask <question>                        Ask Mini-Igor using the current CAM world.
  reset                                 Erase the in-memory world and return to an empty CAM.
  quit                                  Exit.

World-building notes:
  - The world starts EMPTY. Nothing about Alric or anyone else is prewritten.
  - All edits are in memory only. This playground does not modify seed.py or write a world file.
  - Questions must explicitly mention at least one stored Concept or alias so CAM can activate a starting point.
  - Each ask starts a fresh reasoning session against the world as it exists at that moment.
  - Mini-Igor uses the V1 CAM-native contract and the same rich Packet #1 behavior used in the V1 tests.
  - CAM supplies memory; Mini-Igor reasons. Unsupported conclusions are still possible and are part of the experiment.
"""


def empty_world() -> DesignMemory:
    return DesignMemory((), (), ())


def parse_state(raw: str) -> EvidenceState:
    normalized = raw.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "locked": EvidenceState.LOCKED,
        "proven": EvidenceState.PROVEN,
        "experimentally_proven": EvidenceState.PROVEN,
        "hypothesis": EvidenceState.HYPOTHESIS,
        "parked": EvidenceState.PARKED,
        "rejected": EvidenceState.REJECTED,
        "unresolved": EvidenceState.UNRESOLVED,
    }
    if normalized not in aliases:
        raise ValueError(
            "state must be one of: locked, proven, hypothesis, parked, rejected, unresolved"
        )
    return aliases[normalized]


def csv_values(raw: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in raw.split(",") if value.strip())


def show_summary(memory: DesignMemory) -> None:
    print("\nWORLD SUMMARY")
    print(f"Concepts: {len(memory.concepts)}")
    print(f"Associations: {len(memory.associations)}")
    print(f"Historical Occurrences: {len(memory.occurrences)}")


def list_concepts(memory: DesignMemory) -> None:
    print("\nCONCEPTS")
    if not memory.concepts:
        print("- none")
        return
    for concept in sorted(memory.concepts.values(), key=lambda item: item.name.casefold()):
        aliases = ", ".join(concept.aliases) if concept.aliases else "none"
        print(f"- {concept.name} | synopsis={concept.synopsis!r} | aliases={aliases}")


def list_associations(memory: DesignMemory) -> None:
    print("\nASSOCIATIONS")
    if not memory.associations:
        print("- none")
        return
    for association in memory.associations:
        provenance = ", ".join(association.provenance) if association.provenance else "none"
        print(f"- {association.render()} | provenance={provenance}")


def list_history(memory: DesignMemory) -> None:
    print("\nHISTORICAL OCCURRENCES")
    if not memory.occurrences:
        print("- none")
        return
    for occurrence in memory.occurrences:
        participants = ", ".join(occurrence.participants) if occurrence.participants else "none"
        print(f"- {occurrence.render()} | participants={participants}")


def show_concept(memory: DesignMemory, requested: str) -> None:
    key = requested.strip().casefold()
    canonical = memory._aliases.get(key)
    if canonical is None or canonical not in memory.concepts:
        print(f"Concept not found: {requested}")
        return
    concept = memory.concepts[canonical]
    print(f"\nCONCEPT: {concept.name}")
    print(f"Synopsis: {concept.synopsis}")
    print(f"Description: {concept.description}")
    print(f"Aliases: {', '.join(concept.aliases) if concept.aliases else 'none'}")


def add_concept(interface: MemoryInterface) -> None:
    print("\nADD CONCEPT")
    name = input("name> ").strip()
    synopsis = input("synopsis> ").strip()
    description = input("description> ").strip()
    aliases = csv_values(input("aliases (comma-separated, blank for none)> "))
    try:
        interface.add_concept(name, synopsis, description, aliases)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Concept: {name}")


def add_association(interface: MemoryInterface) -> None:
    print("\nADD ASSOCIATION")
    evidence_id = input("evidence id> ").strip()
    source = input("source concept> ").strip()
    relationship = input("relationship> ").strip()
    target = input("target concept or literal value> ").strip()
    raw_state = input("state [locked/proven/hypothesis/parked/rejected/unresolved]> ").strip()
    provenance = csv_values(input("provenance IDs (comma-separated, blank for none)> "))
    try:
        state = parse_state(raw_state)
        if source not in interface.memory.concepts:
            raise ValueError(f"source Concept does not exist: {source}")
        interface.add_association(evidence_id, source, relationship, target, state, provenance)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Association: {evidence_id}")


def add_occurrence(interface: MemoryInterface) -> None:
    print("\nADD HISTORICAL OCCURRENCE")
    evidence_id = input("evidence id> ").strip()
    date = input("date / WorldTime text> ").strip()
    participants = csv_values(input("participants (comma-separated Concept names)> "))
    story = input("what happened> ").strip()
    raw_state = input("state [locked/proven/hypothesis/parked/rejected/unresolved]> ").strip()
    try:
        state = parse_state(raw_state)
        missing = [name for name in participants if name not in interface.memory.concepts]
        if missing:
            raise ValueError(f"participant Concepts do not exist: {', '.join(missing)}")
        interface.add_occurrence(evidence_id, date, participants, story, state)
    except ValueError as exc:
        print(f"Not added: {exc}")
        return
    print(f"Added Historical Occurrence: {evidence_id}")


def show_integrity(interface: MemoryInterface) -> None:
    report = interface.integrity_report()
    print("\nMEMORY INTEGRITY")
    if report.clean:
        print("clean")
        return
    print("Dangling Association sources:", ", ".join(report.dangling_association_sources) or "none")
    print("Dangling Association targets:", ", ".join(report.dangling_association_targets) or "none")
    print("Dangling Historical Occurrence participants:", ", ".join(report.dangling_occurrence_participants) or "none")


def configure_v1_world_handshake(memory: DesignMemory) -> None:
    """Reuse the known-good V1 handshake against this mutable world instance."""
    handshake.WIRETAP_SYSTEM_PROMPT = CAM_NATIVE_SYSTEM_PROMPT
    handshake.execute_memory_action = native._strict_execute_memory_action
    handshake.INITIAL_BUDGET = native.RICH_INITIAL_BUDGET
    handshake.DesignMemory.build_initial_packet = native._rich_build_initial_packet
    handshake.build_memory = lambda: memory


def ask_mini_igor(
    memory: DesignMemory,
    provider: LlamaCppCamNativeProvider,
    question: str,
    max_rounds: int,
) -> None:
    if not memory.concepts:
        print("The world is empty. Add at least one Concept first.")
        return
    configure_v1_world_handshake(memory)
    result = handshake.run_question(
        question,
        provider_fn=provider,
        max_rounds=max_rounds,
        verbose=True,
    )
    print("\nMINI-IGOR RESULT")
    print(f"status={result.status}")
    if result.answer is not None:
        print(f"answer={result.answer}")
        print(f"evidence={', '.join(result.evidence_ids) if result.evidence_ids else 'none'}")
    if result.error is not None:
        print(f"error={result.error}")
    print(
        f"wall={result.total_elapsed_ms:.1f} ms | provider={result.total_provider_ms:.1f} ms | "
        f"CAM={result.total_cam_ms:.3f} ms | LLM_calls={len(result.rounds)} | "
        f"CAM_packet_est_tokens={result.cam_packet_estimated_tokens}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively build a CAM world and let V1 Mini-Igor reason over it."
    )
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--llama-model", default="cam-native-v1")
    parser.add_argument("--max-rounds", type=int, default=5)
    args = parser.parse_args()

    world = empty_world()
    interface = MemoryInterface(world)
    provider = LlamaCppCamNativeProvider(base_url=args.llama_url, model=args.llama_model)

    print("CHRONOSPEAR MINI-IGOR WORLD PLAYGROUND")
    print(f"provider=llama.cpp / {args.llama_model} @ {args.llama_url}")
    print("world=EMPTY mutable CAM")
    print("Mini-Igor=V1 CAM-native reasoner")
    print("Type 'help' for commands.")

    while True:
        raw = input("world> ").strip()
        if not raw:
            continue
        command, _, argument = raw.partition(" ")
        command = command.casefold()
        argument = argument.strip()

        if command in {"quit", "exit"}:
            return
        if command == "help":
            print(HELP)
        elif command == "summary":
            show_summary(world)
        elif command == "concepts":
            list_concepts(world)
        elif command == "associations":
            list_associations(world)
        elif command in {"history", "occurrences"}:
            list_history(world)
        elif command == "show":
            show_concept(world, argument)
        elif command == "integrity":
            show_integrity(interface)
        elif command == "add":
            kind = argument.casefold()
            if kind == "concept":
                add_concept(interface)
            elif kind == "association":
                add_association(interface)
            elif kind in {"occurrence", "history"}:
                add_occurrence(interface)
            else:
                print("Usage: add concept | add association | add occurrence")
        elif command == "remove":
            kind, _, target = argument.partition(" ")
            kind = kind.casefold()
            target = target.strip()
            if not target:
                print("Usage: remove concept <name> | association <id> | occurrence <id>")
                continue
            try:
                if kind == "concept":
                    removed = interface.remove_concept(target)
                    print(f"Removed Concept only: {removed.name}")
                    print("References were not cascaded. Run 'integrity'.")
                elif kind == "association":
                    removed = interface.remove_association(target)
                    print(f"Removed Association: {removed.id}")
                elif kind in {"occurrence", "history"}:
                    removed = interface.remove_occurrence(target)
                    print(f"Removed Historical Occurrence: {removed.id}")
                else:
                    print("Usage: remove concept|association|occurrence <name-or-id>")
            except KeyError:
                print(f"Nothing removed; not found: {target}")
        elif command == "ask":
            if not argument:
                argument = input("question> ").strip()
            if argument:
                ask_mini_igor(world, provider, argument, args.max_rounds)
        elif command == "reset":
            world = empty_world()
            interface = MemoryInterface(world)
            print("World reset to an empty CAM.")
        else:
            print("Unknown command. Type 'help'.")


if __name__ == "__main__":
    main()
