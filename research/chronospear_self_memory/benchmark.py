from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuestCase:
    question: str
    expected_support_any: frozenset[str]
    review_note: str


QUESTS = (
    QuestCase(
        "What is a Description allowed to contain?",
        frozenset({"o-0826-desc", "a-desc-1"}),
        "Should say stable identity clarification only; mutable/secret/perspective facts belong elsewhere.",
    ),
    QuestCase(
        "Why is Relationship Type not an Identity Node?",
        frozenset({"o-0826-rel", "a-rel-1"}),
        "Should distinguish controlled semantic vocabulary from enduring identity objects.",
    ),
    QuestCase(
        "Does the Language Surface turn the word where into CURRENT_LOCATION?",
        frozenset({"o-0830-language", "a-lang-1"}),
        "Should answer no and preserve the LLM-vs-CAM reasoning boundary.",
    ),
    QuestCase(
        "What evidence do we have that Packet #1 can stay question-agnostic?",
        frozenset({"o-0831-live", "a-packet-2"}),
        "Should cite the 8/31 live probe, not merely the 8/30 hypothesis.",
    ),
    QuestCase(
        "What did the fixed widening Expansion experiment show?",
        frozenset({"o-0831-widen", "a-expand-2"}),
        "Should mention one new Alric->Royal Guard link enabled direct and multi-hop reasoning.",
    ),
    QuestCase(
        "What semantic risk did the Expansion experiment expose?",
        frozenset({"o-0831-overreach"}),
        "Should mention MEMBER_OF->works-for strengthening and/or unsupported kingdom premise.",
    ),
    QuestCase(
        "What does COLD mean in HOT/WARM/COLD?",
        frozenset({"o-0830-temp", "a-temp-1"}),
        "Should say eligible for evaluation, not proof of change and not automatic deletion.",
    ),
    QuestCase(
        "What is still unresolved about MCP?",
        frozenset({"o-0830-mcp", "a-mcp-1"}),
        "Should preserve that the exact MCP contract remains unresolved.",
    ),
    QuestCase(
        "How is our thinking about Expansion changing on 8/31?",
        frozenset({"o-0831-widen", "o-0831-delta", "o-0831-map"}),
        "Should separate proven fixed widening from newer delta/map hypotheses.",
    ),
)
