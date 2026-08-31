from __future__ import annotations

from memory import Concept, DesignAssociation, DesignMemory, DesignOccurrence, EvidenceState


def build_memory() -> DesignMemory:
    concepts = (
        Concept(
            "Description",
            "Stable clarification of what an identity is.",
            "Identity clarification only; it must not carry mutable, secret, temporal, or perspective-dependent world facts.",
            ("Node Description", "Descriptions"),
        ),
        Concept(
            "Identity Node",
            "An enduring addressable identity or concept in CAM.",
            "The locked Slice 1 identity families are Entity, Place, and Describer.",
            ("IdentityNode",),
        ),
        Concept(
            "Relationship Type",
            "Controlled semantic vocabulary used by Associations.",
            "A Relationship Type defines intentional relation semantics and is not an Identity Node.",
            ("RelationshipType", "Relationship Types"),
        ),
        Concept(
            "Historical Occurrence",
            "Immutable historical evidence describing what happened in-world.",
            "Historical Occurrences are blue occurrence hubs, distinct from Identity Nodes, and preserve canonical history.",
            ("Historical Occurrences", "History"),
        ),
        Concept(
            "Association",
            "Plastic, addressable semantic knowledge connecting identities.",
            "Associations represent useful relational knowledge and may be reconstructed from preserved history.",
            ("Associations",),
        ),
        Concept(
            "Language Surface",
            "The linguistic access layer that maps explicit language to CAM objects.",
            "Language Surfaces are semantic access points, not world truth and not a general query reasoner.",
            ("Language Node", "Language Nodes"),
        ),
        Concept(
            "Packet #1",
            "The first small deterministic memory packet supplied to an LLM reasoning session.",
            "Packet #1 is intended to provide bounded starting evidence, not necessarily the complete answer.",
            ("Packet 1", "Initial Packet", "first packet"),
        ),
        Concept(
            "Expansion",
            "Bounded progressive disclosure of additional CAM memory after Packet #1.",
            "Expansion is being researched as a way to reveal more memory without making the initial packet large.",
            ("memory expansion", "expansions"),
        ),
        Concept(
            "HOT/WARM/COLD",
            "An optional activation/evaluation wrapper over existing CAM elements.",
            "COLD means eligible for evaluation, not automatically wrong or deletable.",
            ("HOT WARM COLD", "COLD", "activation wrapper"),
        ),
        Concept(
            "MCP",
            "The Memory Creation Protocol that reconciles proposed post-interaction memory changes.",
            "MCP is a construction/reconciliation boundary; exact contract remains unresolved.",
            ("Memory Creation Protocol",),
        ),
        Concept(
            "CAM",
            "Chrono Associative Memory, combining preserved history with plastic associative knowledge.",
            "CAM is ChronoSpear's persistent memory authority.",
            ("Chrono Associative Memory",),
        ),
        Concept(
            "LLM",
            "The temporary reasoning and language component operating on bounded CAM evidence.",
            "The LLM interprets language, reasons, narrates, and may request more memory; its output is not persistent truth by itself.",
            ("model", "reasoner"),
        ),
    )

    associations = (
        DesignAssociation("a-desc-1", "Description", "PURPOSE", "Identity Node", EvidenceState.LOCKED, ("o-0826-desc",)),
        DesignAssociation("a-rel-1", "Relationship Type", "IS_NOT", "Identity Node", EvidenceState.LOCKED, ("o-0826-rel",)),
        DesignAssociation("a-hist-1", "Historical Occurrence", "IS_DISTINCT_FROM", "Identity Node", EvidenceState.LOCKED, ("o-0826-history",)),
        DesignAssociation("a-cam-1", "CAM", "PERSISTENT_MEMORY_AUTHORITY_FOR", "LLM", EvidenceState.LOCKED, ("o-0826-cam",)),
        DesignAssociation("a-lang-1", "Language Surface", "MUST_NOT_INFER", "query meaning beyond explicit CAM object activation", EvidenceState.LOCKED, ("o-0830-language",)),
        DesignAssociation("a-packet-1", "Packet #1", "SHOULD_BE", "mechanically built from activated CAM objects under a small fixed budget", EvidenceState.HYPOTHESIS, ("o-0830-packet",)),
        DesignAssociation("a-packet-2", "Packet #1", "SUPPORTED_USE", "LLM can decide answer-vs-request-more from a question-agnostic packet", EvidenceState.PROVEN, ("o-0831-live",)),
        DesignAssociation("a-expand-1", "Expansion", "SHOULD_SEND", "only CAM evidence not already admitted to the action session", EvidenceState.HYPOTHESIS, ("o-0831-delta",)),
        DesignAssociation("a-expand-2", "Expansion", "SUPPORTED_USE", "bounded request-agnostic widening can enable multi-hop LLM reasoning", EvidenceState.PROVEN, ("o-0831-widen",)),
        DesignAssociation("a-temp-1", "HOT/WARM/COLD", "WRAPS", "CAM", EvidenceState.HYPOTHESIS, ("o-0830-temp",)),
        DesignAssociation("a-mcp-1", "MCP", "VALIDATES_OUTPUT_FROM", "LLM", EvidenceState.HYPOTHESIS, ("o-0830-mcp",)),
    )

    occurrences = (
        DesignOccurrence(
            "o-0826-desc",
            "2026-08-26",
            ("Description", "Identity Node", "Association", "Historical Occurrence"),
            "Locked the rule that Node Description explains what an identity is and must not smuggle mutable, secret, or perspective-dependent facts into the Interpreter; those belong in Associations and History.",
            EvidenceState.LOCKED,
        ),
        DesignOccurrence(
            "o-0826-rel",
            "2026-08-26",
            ("Relationship Type", "Identity Node", "Association"),
            "Locked Relationship Type as controlled semantic vocabulary rather than an Identity Node; Associations use that vocabulary and the LLM may not silently invent durable Relationship Types.",
            EvidenceState.LOCKED,
        ),
        DesignOccurrence(
            "o-0826-history",
            "2026-08-26",
            ("Historical Occurrence", "Identity Node", "Association"),
            "Established the graph-shaped Historical Occurrence model: history preserves immutable occurrence hubs while associative memory remains plastic.",
            EvidenceState.PROVEN,
        ),
        DesignOccurrence(
            "o-0826-cam",
            "2026-08-26",
            ("CAM", "LLM"),
            "Locked the core boundary that CAM is persistent memory authority while the LLM reasons from bounded evidence and does not become authoritative memory by itself.",
            EvidenceState.LOCKED,
        ),
        DesignOccurrence(
            "o-0830-language",
            "2026-08-30",
            ("Language Surface", "CAM", "LLM"),
            "Corrected the Language Surface direction: the word 'where' should not be converted into CURRENT_LOCATION merely to answer a location question. Language activates explicit CAM objects; the LLM understands query meaning.",
            EvidenceState.LOCKED,
        ),
        DesignOccurrence(
            "o-0830-temp",
            "2026-08-30",
            ("HOT/WARM/COLD", "CAM"),
            "Retained HOT/WARM/COLD as an optional activation wrapper. COLD means eligible for evaluation, not universally delete and not proof that the wrapped knowledge changed.",
            EvidenceState.HYPOTHESIS,
        ),
        DesignOccurrence(
            "o-0830-packet",
            "2026-08-30",
            ("Packet #1", "CAM", "LLM", "Expansion"),
            "Formed the hypothesis that Packet #1 should be built mechanically from explicitly activated CAM objects using a small predictable budget; it need not contain the answer because reactive expansion can provide more evidence.",
            EvidenceState.HYPOTHESIS,
        ),
        DesignOccurrence(
            "o-0830-mcp",
            "2026-08-30",
            ("MCP", "LLM", "CAM"),
            "Reframed MCP as a construction/reconciliation mechanism. The LLM may return a historical synopsis and memory candidates, but MCP/CAM controls durable persistence. Exact MCP contract remains unresolved.",
            EvidenceState.UNRESOLVED,
        ),
        DesignOccurrence(
            "o-0831-live",
            "2026-08-31",
            ("Packet #1", "Expansion", "LLM", "CAM"),
            "Live Groq probe used the same fixed memory neighborhood for four Alric questions. The LLM answered when evidence was sufficient and requested specific additional memory for employer and kingdom questions without CAM interpreting the question semantics.",
            EvidenceState.PROVEN,
        ),
        DesignOccurrence(
            "o-0831-widen",
            "2026-08-31",
            ("Expansion", "Packet #1", "LLM", "CAM"),
            "Fixed request-agnostic widening exposed only 'Alric MEMBER_OF Royal Guard'. The LLM then answered Royal Guard for the employment-style question and combined that new link with prior packet evidence to answer Northmarch for a three-hop kingdom connection question.",
            EvidenceState.PROVEN,
        ),
        DesignOccurrence(
            "o-0831-overreach",
            "2026-08-31",
            ("LLM", "Association", "Expansion"),
            "The same widening probe exposed semantic overreach: the LLM strengthened MEMBER_OF into 'works for' and may have accepted an unsupported premise that Northmarch is a kingdom. This is an Interpreter-boundary risk, not a CAM retrieval success criterion.",
            EvidenceState.PROVEN,
        ),
        DesignOccurrence(
            "o-0831-delta",
            "2026-08-31",
            ("Expansion", "Packet #1", "CAM"),
            "Proposed that later CAM expansion packets should be deltas: compare candidate evidence with what the action session has already seen and transmit only genuinely new CAM memory. Nothing is deleted from CAM.",
            EvidenceState.HYPOTHESIS,
        ),
        DesignOccurrence(
            "o-0831-map",
            "2026-08-31",
            ("Expansion", "CAM", "LLM"),
            "Proposed a temporary per-action memory availability map: surfaced concepts report whether more description, associations, or history exist, letting the LLM ask for bounded expansion without seeing unrestricted graph structure.",
            EvidenceState.HYPOTHESIS,
        ),
    )
    return DesignMemory(concepts, associations, occurrences)
