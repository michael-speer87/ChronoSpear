# Production Slice 2 — Immutable Historical Occurrences

## Purpose

Add the smallest canonical representation of world History to production CAM without introducing recall, lifecycle, provenance, correction, persistence, or LLM behavior.

Slice 1 established Identity, Association, Relationship Type, WorldTime, SystemTime, and ChronoStamp. Slice 2 adds the blue half of CAM: an immutable record that something happened in the represented world.

## Architectural role

Historical Occurrence answers **what happened**. It is persistent world History and is conceptually distinct from plastic associative knowledge.

An occurrence is graph-addressable, but it is **not** an `IdentityNode`, is **not** an `Association`, and must not be forced into a universal Node hierarchy.

Canonical Slice 2 shape:

`OccurrenceId + ChronoStamp + one-or-more Entity participant IdentityIds + required Place IdentityId + synopsis + story`

## Must do

- Add stable type-specific `OccurrenceId` values.
- Represent `HistoricalOccurrence` as immutable.
- Capture one immutable `ChronoStamp` containing both WorldTime and SystemTime.
- Require one or more participant `IdentityId` values.
- Require one explicit place `IdentityId`.
- Require every participant to resolve to an existing `IdentityKind.ENTITY` identity.
- Forbid Place and Describer identities from the participant list.
- Require the place to resolve to an existing `IdentityKind.PLACE` identity.
- Require non-empty synopsis and story text.
- Preserve participant order supplied by the caller.
- Reject duplicate participant IDs inside one occurrence rather than silently normalizing them.
- Provide a minimal in-memory `OccurrenceCatalog` supporting `add`, `get`, and `all`.
- Make exact re-addition of the same occurrence ID and same occurrence idempotent.
- Reject reuse of one `OccurrenceId` for conflicting occurrence data.
- Permit different Occurrence IDs to carry otherwise identical event data. Slice 2 does not define semantic event deduplication.
- Permit multiple occurrences to carry equal WorldTime/SystemTime coordinates. Equal timestamps are not competing truth by themselves.
- Export Slice 2 types from the public `chronospear.cam` API.

## Must not do

- No mutation/edit/delete of Historical Occurrences.
- No Amend/Void/VARA implementation.
- No Association ↔ Historical Occurrence support/provenance graph.
- No Association lifecycle FUTURE/EFFECTIVE/ENDED resolution.
- No Perspective / KNOWS.
- No Language Surface implementation.
- No Action Reasoning Session.
- No Memory Creation Protocol.
- No Interaction/Chat Log.
- No Cleaner, decay, or Audit implementation.
- No Calendar implementation.
- No SQLite/database persistence.
- No graph traversal, recall, packet building, semantic ranking, embeddings, or GraphRAG.
- No UI/API server.
- No LLM/provider integration.
- No generic graph-object superclass.
- No semantic duplicate detection for Historical Occurrences.

## Historical Occurrence semantics

### Identity versus History

Identity answers **what something is**.

History answers **what happened**.

Example:

- Identity: `Alric` is an Entity.
- Association: `Alric --MEMBER_OF--> Royal Guard` is plastic semantic knowledge.
- Historical Occurrence: `At WT 300, Alric joined the Royal Guard at Stonebridge.` is immutable world History.

A later Association may be derived from or supported by that History, but Slice 2 does not create that support relationship.

### Participants

`participants` answers **which enduring Entities were involved in the occurrence**.

Every participant must reference an existing `IdentityKind.ENTITY`. Places have their own required field, and Describers are classification concepts rather than event participants.

### Synopsis versus story

Both are required and have different roles:

- `synopsis` is a compact account suitable for cheap orientation/recall in later slices.
- `story` is the preserved fuller account of what happened.

Slice 2 stores both but does not generate, summarize, rank, or interpret either field.

### Place

`place` is a required graph anchor and must reference an existing `IdentityKind.PLACE` identity through its `IdentityId`.

Location meaning is not embedded into Entity records.

### Time

Every occurrence contains one `ChronoStamp`:

- `stamp.world_time` = when the event happened in the represented world.
- `stamp.system_time` = when ChronoSpear learned/accepted this occurrence record.

ChronoStamp remains a captured coordinate pair, not a clock owner.

## Invariants

1. HistoricalOccurrence != IdentityNode.
2. HistoricalOccurrence != Association.
3. OccurrenceId != IdentityId != AssociationId.
4. Historical Occurrence records are immutable after construction.
5. An occurrence must contain at least one Entity participant.
6. Every participant must resolve to `IdentityKind.ENTITY`.
7. Describer and Place identities cannot be event participants.
8. Every occurrence must contain one required Place identity.
9. The place must resolve to `IdentityKind.PLACE`.
10. Synopsis and story cannot be blank.
11. Duplicate participants in one occurrence are rejected.
12. One OccurrenceId cannot identify two different occurrence records.
13. Different OccurrenceIds are not semantically deduplicated merely because their payloads match.
14. Equal ChronoStamp coordinate values across separate occurrences are allowed.
15. Slice 2 creates no relationship from History to Associations.
16. Slice 2 provides no path for mutating or deleting admitted History.

## Acceptance behavior

The test suite must prove:

- Occurrence IDs reject blanks and generated IDs are unique.
- Historical Occurrence records are immutable.
- Synopsis/story whitespace is normalized and blank values are rejected.
- At least one participant is required.
- Duplicate participant IDs are rejected.
- Known Entity participant IDs are accepted.
- Unknown participant IDs are rejected by `OccurrenceCatalog`.
- Place identities cannot be used as participants.
- Describer identities cannot be used as participants.
- A known Place identity is accepted as the required `place`.
- An unknown place ID is rejected.
- A non-Place identity cannot be used as `place`.
- Re-adding the exact same occurrence is idempotent.
- Reusing an OccurrenceId for different data is rejected.
- Two otherwise identical events with different OccurrenceIds can coexist.
- Two separate events may use equal ChronoStamp values.
- Slice 1 behavior remains unchanged.
- Slice 2 types are importable from `chronospear.cam`.

## Taxation

No recall/query taxation framework is introduced in Slice 2. `OccurrenceCatalog` is an invariant keeper, not a retrieval engine. It may use a dictionary keyed by `OccurrenceId` for local add/get behavior.

## Done when

- `pytest` passes.
- `ruff check .` passes where the local environment permits running ruff.
- `mypy` passes in strict mode.
- The code obeys `AGENTS.md` and this contract.
- No out-of-scope CAM or LLM behavior has been scaffolded into production.
