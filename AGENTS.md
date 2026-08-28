# ChronoSpear Agent Constitution

This repository is architecture-sensitive. Read this file before making changes.

## Project identity

ChronoSpear is a **historical reasoning brain** built around **Chrono Associative Memory (CAM)**. TTRPG play is its first major application, not the definition of the architecture.

## Non-negotiable architecture rules

1. **CAM is persistent memory authority.** LLM/provider context is temporary reasoning context, not authoritative memory.
2. **History preserves; associative memory adapts.** Do not merge immutable historical truth and plastic associative knowledge into one mutable record model.
3. **Identity Nodes are not all graph objects.** `IdentityNode` currently means Entity, Place, or Describer only.
4. **Do not create a universal MegaNode base class.** Historical Occurrences, Amend, Void, Audit, Calendar, Language objects, and Associations have different semantics even if graph-addressable.
5. **Association is an addressable semantic assertion, not an anonymous edge and not an Identity Node.**
6. **RelationshipType is controlled semantic vocabulary, not a Node.** AI/LLM code must never silently create durable Relationship Types.
7. **Descriptions define identity only.** Mutable, secret, temporal, or perspective-dependent facts belong in Associations/History.
8. **WorldTime and SystemTime are different coordinates.** WT = when something happens/applies in-world. ST = when ChronoSpear learns/accepts information.
9. **ChronoStamp is an immutable captured pair of WT + ST, not a clock.** Do not create competing `current_time` authorities inside records/components.
10. **Do not replace typed time with ambiguous raw `tick: int` fields.** If a field means WT or ST, use the corresponding type. If it needs both, use `ChronoStamp`.
11. **Language Surfaces are semantic access points, not world truth.** They will be implemented later and must be able to target Nodes, Relationship Types, Associations, and other controlled CAM semantics without bypassing policy.
12. **Perspective filtering happens before LLM evidence exposure.** Never rely on prompts to hide already-supplied secrets.
13. **LLM sessions are ephemeral per player action.** Future conversation history may be reconstructed from a persisted Interaction Log, but provider conversation state is not persistent memory.
14. **Persistent writes cross a Memory Creation Protocol.** An LLM result is a proposal/conclusion, not world truth until validated.
15. **Prefer local indexed work and measurable taxation.** Do not introduce global scans when a local/indexed seam can preserve behavior.
16. **Do not invent architecture to make a task convenient.** If a required policy is not specified, preserve the seam, document the question, and stop at the agreed slice boundary.
17. **Do not resurrect legacy DungeonMind assumptions by default.** Legacy code is a parts bin, not architectural authority. Example: Entity must not own Place; location is relational knowledge.

## Slice discipline

Each production slice is discussed/refined before implementation. Implement only the active slice and its acceptance contract. Do not scaffold future systems unless the contract explicitly requires a seam.

Workflow:

`Discuss → Refine → Specify → Implement → Test → Git → Review → Repeat`

## Current active slice

**Production Slice 1: CAM Core Primitives**

See `docs/SLICE_1_CONTRACT.md`. Anything listed as out of scope there must not be implemented without a newer explicit handoff.
