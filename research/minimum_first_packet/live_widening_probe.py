from __future__ import annotations

import json

from experiment import DecisionKind, PacketSource
from live_probe import build_packet, call_groq
from widening import ExpansionBudget, FixedWideningProvider


def build_source(question: str) -> PacketSource:
    return PacketSource(
        perspective="Dorf",
        latest_interaction=question,
        activated_objects=build_packet(question).activated_objects,
        recent_chat=("Dorf asked about Elara.", "Dorf turned back to Alric."),
        recent_history=(
            "WT100: Alric entered the Black Stag.",
            "WT110: Alric ordered an ale.",
            "WT120: Alric spoke with Elara by the fireplace.",
            "WT130: Dorf left the Black Stag.",
        ),
        effective_associations=(
            "Alric MEMBER_OF Royal Guard",
            "Royal Guard BASED_IN Stonebridge",
            "Stonebridge PART_OF Northmarch",
        ),
    )


def main() -> None:
    questions = (
        "Who does Alric work for?",
        "What kingdom is Alric connected to?",
    )

    for question in questions:
        source = build_source(question)
        packet = build_packet(question)

        print("=" * 72)
        print(f"QUESTION: {question}")
        print(
            "INITIAL TAXATION: "
            f"history={packet.taxation.history_items}, "
            f"associations={packet.taxation.association_items}, "
            f"chat={packet.taxation.chat_items}, "
            f"estimated_tokens={packet.taxation.estimated_tokens}"
        )

        first, first_usage = call_groq(packet.render())
        print(f"FIRST DECISION: {first.kind.value}")
        print(f"FIRST TEXT: {first.text}")
        print(f"FIRST PROVIDER USAGE: {json.dumps(first_usage, sort_keys=True)}")

        if first.kind is DecisionKind.ANSWER:
            print("No widening requested.")
            continue

        widening = FixedWideningProvider(
            source,
            packet,
            ExpansionBudget(recent_history=0, effective_associations=1),
        ).expand(first.text)

        print(f"MODEL REQUEST: {widening.request}")
        print(
            "EXPANSION TAXATION: "
            f"history={widening.taxation.history_items}, "
            f"associations={widening.taxation.association_items}, "
            f"estimated_tokens={widening.taxation.estimated_tokens}"
        )
        print("EXPANSION MEMORY:")
        print(widening.render())

        follow_up = (
            f"{packet.render()}\n\n"
            f"YOUR PREVIOUS MEMORY REQUEST:\n{first.text}\n\n"
            f"ADDITIONAL MEMORY:\n{widening.render()}\n\n"
            "Re-evaluate the original question using the original packet plus this additional "
            "memory. Reply using the same ANSWER or REQUEST_MORE contract."
        )
        final, final_usage = call_groq(follow_up)
        print(f"FINAL DECISION: {final.kind.value}")
        print(f"FINAL TEXT: {final.text}")
        print(f"FINAL PROVIDER USAGE: {json.dumps(final_usage, sort_keys=True)}")


if __name__ == "__main__":
    main()
