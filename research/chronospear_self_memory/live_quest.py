from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request

from benchmark import QUESTS, QuestCase
from memory import MemoryPacket, MemorySession, PacketBudget
from seed import build_memory


SYSTEM_PROMPT = """You are the reasoning component in the ChronoSpear self-memory research quest.
You receive incremental CAM memory packets from one per-question reasoning session.
Use only supplied evidence. Respect evidence-state labels exactly:
LOCKED=current architecture, EXPERIMENTALLY_PROVEN=test evidence, HYPOTHESIS=not locked,
PARKED=deferred, REJECTED=historical only, UNRESOLVED=open question.
Never upgrade a hypothesis into a decision.

If you can answer, reply exactly in this two-line form:
ANSWER: <concise answer>
EVIDENCE: <comma-separated evidence IDs such as o-0831-live,a-packet-2>

If you need more memory, reply exactly:
REQUEST_MORE: <ordinary-language request that explicitly names ONE concept visible in the memory availability map>
"""


@dataclass(frozen=True)
class ProviderResult:
    text: str
    usage: dict[str, object]


@dataclass(frozen=True)
class Decision:
    kind: str
    text: str
    evidence_ids: tuple[str, ...] = ()


def parse_decision(text: str) -> Decision:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty model response")
    if lines[0].startswith("REQUEST_MORE:"):
        return Decision("request_more", lines[0].removeprefix("REQUEST_MORE:").strip())
    if lines[0].startswith("ANSWER:"):
        answer = lines[0].removeprefix("ANSWER:").strip()
        evidence_line = next((line for line in lines[1:] if line.startswith("EVIDENCE:")), "")
        evidence = evidence_line.removeprefix("EVIDENCE:").strip()
        ids = tuple(item.strip() for item in evidence.split(",") if item.strip())
        return Decision("answer", answer, ids)
    raise ValueError(f"unexpected model response: {text!r}")


def call_provider(messages: list[dict[str, str]]) -> ProviderResult:
    provider = os.environ.get("CS_DESIGN_PROVIDER", "groq").casefold()
    if provider == "groq":
        return call_groq(messages)
    if provider == "ollama":
        return call_ollama(messages)
    raise RuntimeError("CS_DESIGN_PROVIDER must be 'groq' or 'ollama'")


def call_groq(messages: list[dict[str, str]]) -> ProviderResult:
    api_key = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("GROQ_MODEL")
    if not api_key or not model:
        raise RuntimeError("GROQ_API_KEY and GROQ_MODEL must be set for Groq")
    return call_groq_model(messages, model, api_key=api_key)


def call_groq_model(
    messages: list[dict[str, str]],
    model: str,
    *,
    api_key: str | None = None,
) -> ProviderResult:
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY must be set for Groq")
    body = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
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
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Groq HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    return ProviderResult(payload["choices"][0]["message"]["content"], payload.get("usage", {}))


def call_ollama(messages: list[dict[str, str]]) -> ProviderResult:
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    body = json.dumps(
        {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0}}
    ).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach Ollama at http://127.0.0.1:11434") from exc
    usage = {
        "prompt_tokens": payload.get("prompt_eval_count", 0),
        "completion_tokens": payload.get("eval_count", 0),
    }
    return ProviderResult(payload["message"]["content"], usage)


def packet_tax(packet: MemoryPacket) -> str:
    return (
        f"new_synopses={len(packet.new_synopses)}, "
        f"full_descriptions={len(packet.full_descriptions)}, "
        f"associations={len(packet.associations)}, history={len(packet.history)}, "
        f"estimated_tokens={packet.estimated_tokens}"
    )


def run_case(case: QuestCase) -> None:
    memory = build_memory()
    session = MemorySession()
    budget = PacketBudget(associations_per_concept=1, history_per_concept=1)
    packet = memory.build_initial_packet(case.question, session, budget)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": packet.render()},
    ]
    cam_tokens = packet.estimated_tokens

    print("=" * 88)
    print(f"QUESTION: {case.question}")
    print(f"INITIAL CAM DELTA: {packet_tax(packet)}")

    for round_number in range(1, 5):
        result = call_provider(messages)
        decision = parse_decision(result.text)
        print(f"ROUND {round_number} DECISION: {decision.kind}")
        print(f"ROUND {round_number} TEXT: {decision.text}")
        print(f"ROUND {round_number} PROVIDER USAGE: {json.dumps(result.usage, sort_keys=True)}")
        messages.append({"role": "assistant", "content": result.text})

        if decision.kind == "answer":
            evidence_match = bool(set(decision.evidence_ids) & set(case.expected_support_any))
            print(f"EVIDENCE IDS: {decision.evidence_ids}")
            print(f"EXPECTED-SUPPORT HIT: {evidence_match}")
            print(f"CAM NEW-MEMORY TOKENS (estimated cumulative): {cam_tokens}")
            print(f"HUMAN REVIEW TARGET: {case.review_note}")
            return

        concept = memory.resolve_surfaced_request(decision.text, session)
        if concept is None:
            print("QUEST FAILURE: request did not explicitly name a surfaced concept")
            return

        expansion = memory.expand(concept, session, budget)
        cam_tokens += expansion.estimated_tokens
        print(f"EXPANDING: {concept}")
        print(f"CAM DELTA: {packet_tax(expansion)}")
        if not (
            expansion.new_synopses
            or expansion.full_descriptions
            or expansion.associations
            or expansion.history
        ):
            print("QUEST FAILURE: requested concept has no new evidence left")
            return
        messages.append({"role": "user", "content": expansion.render()})

    print("QUEST FAILURE: expansion-round cap reached")


def main() -> None:
    for case in QUESTS:
        run_case(case)


if __name__ == "__main__":
    main()
