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
7. **The locked core Relationship vocabulary is small and perspective-neutral.** It is exactly `IS_A`, `MEMBER_OF`, `PART_OF`, `LOCATED_IN`, `BASED_IN`, `OWNS`, and `OPPOSES`. Additional durable relationships require intentional extension; do not fold `KNOWS` or arbitrary domain verbs into the core for convenience.
8. **Historical Occurrences require both Entity and Place anchors.** Every occurrence has one or more participants, every participant must resolve to `IdentityKind.ENTITY`, and `place` is required and must resolve to `IdentityKind.PLACE`. Describer and Place identities are not participants.
9. **Descriptions define identity only.** Mutable, secret, temporal, or perspective-dependent facts belong in Associations/History.
10. **WorldTime and SystemTime are different coordinates.** WT = when something happens/applies in-world. ST = when ChronoSpear learns/accepts information.
11. **ChronoStamp is an immutable captured pair of WT + ST, not a clock.** Do not create competing `current_time` authorities inside records/components.
12. **Do not replace typed time with ambiguous raw `tick: int` fields.** If a field means WT or ST, use the corresponding type. If it needs both, use `ChronoStamp`.
13. **Language Surfaces are semantic access points, not world truth.** They will be implemented later and must be able to target Nodes, Relationship Types, Associations, and other controlled CAM semantics without bypassing policy.
14. **Perspective filtering happens before LLM evidence exposure.** Never rely on prompts to hide already-supplied secrets.
15. **LLM sessions are ephemeral per player action.** Future conversation history may be reconstructed from a persisted Interaction Log, but provider conversation state is not persistent memory.
16. **Persistent writes cross a Memory Creation Protocol.** An LLM result is a proposal/conclusion, not world truth until validated.
17. **Campaign persistence is intended to use a human-editable JSON representation.** Loading must validate CAM invariants and preserve stable IDs. A future CAM world editor may safely manipulate the same public campaign representation without exposing every runtime implementation detail.
18. **Prefer local indexed work and measurable taxation.** Do not introduce global scans when a local/indexed seam can preserve behavior.
19. **Do not invent architecture to make a task convenient.** If a required policy is not specified, preserve the seam, document the question, and stop at the agreed slice boundary.
20. **Do not resurrect legacy DungeonMind assumptions by default.** Legacy code is a parts bin, not architectural authority. Example: Entity must not own Place; location is relational knowledge.

## Slice discipline

Each production slice is discussed/refined before implementation. Implement only the active slice and its acceptance contract. Do not scaffold future systems unless the contract explicitly requires a seam.

Workflow:

`Discuss → Refine → Specify → Implement → Test → Git → Review → Repeat`

## Current active slice

**Production Slice 2: Immutable Historical Occurrences**, including the locked foundation refinements documented in the Slice 1 and Slice 2 contracts.

See `docs/SLICE_2_CONTRACT.md`. Slice 1 remains foundational and must continue to pass. Anything listed as out of scope in the active Slice 2 contract must not be implemented without a newer explicit handoff.
