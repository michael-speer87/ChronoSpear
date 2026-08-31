from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from experiment import (
    ActivatedObject,
    DecisionKind,
    InitialPacket,
    InitialPacketBuilder,
    LlmDecision,
    PacketBudget,
    PacketSource,
)


SYSTEM_PROMPT = """You are the reasoning component in a ChronoSpear research experiment.
You receive a bounded memory packet. Do not invent missing facts.
If the packet is enough, reply on one line only:
ANSWER: <answer>
If more memory is needed, reply on one line only:
REQUEST_MORE: <ordinary-language description of the additional memory you need>
"""


def parse_decision(text: str) -> LlmDecision:
    cleaned = text.strip()
    if cleaned.startswith("ANSWER:"):
        return LlmDecision(DecisionKind.ANSWER, cleaned.removeprefix("ANSWER:").strip())
    if cleaned.startswith("REQUEST_MORE:"):
        return LlmDecision(
            DecisionKind.REQUEST_MORE,
            cleaned.removeprefix("REQUEST_MORE:").strip(),
        )
    raise ValueError(f"Unexpected model response: {cleaned!r}")


def call_groq(packet_text: str) -> tuple[LlmDecision, dict[str, object]]:
    api_key = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("GROQ_MODEL")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    if not model:
        raise RuntimeError("GROQ_MODEL is not set")

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": packet_text},
            ],
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ChronoSpear-Research/2026-08-31",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Groq HTTP {exc.code}: {error_body}") from exc

    content = payload["choices"][0]["message"]["content"]
    return parse_decision(content), payload.get("usage", {})


def build_packet(question: str) -> InitialPacket:
    builder = InitialPacketBuilder(
        PacketBudget(recent_chat=2, recent_history=3, effective_associations=2)
    )
    return builder.build(
        PacketSource(
            perspective="Dorf",
            latest_interaction=question,
            activated_objects=(ActivatedObject("Alric", "A human adventurer."),),
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
    )


def main() -> None:
    questions = (
        "Where is Alric?",
        "Who does Alric work for?",
        "What kingdom is Alric connected to?",
        "What did Alric do most recently?",
    )

    for question in questions:
        packet = build_packet(question)
        print("=" * 72)
        print(f"QUESTION: {question}")
        print(
            "PACKET TAXATION: "
            f"history={packet.taxation.history_items}, "
            f"associations={packet.taxation.association_items}, "
            f"chat={packet.taxation.chat_items}, "
            f"estimated_tokens={packet.taxation.estimated_tokens}"
        )
        decision, usage = call_groq(packet.render())
        print(f"DECISION: {decision.kind.value}")
        print(f"TEXT: {decision.text}")
        print(f"PROVIDER USAGE: {json.dumps(usage, sort_keys=True)}")


if __name__ == "__main__":
    main()
