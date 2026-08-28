# Production Slice 1 — CAM Core Primitives

## Purpose

Create the smallest canonical Python vocabulary that later ChronoSpear/CAM slices can depend on without redefining what Identity, Association, Relationship Type, WorldTime, SystemTime, or ChronoStamp mean.

## Architectural role

Slice 1 is the floor, not the brain. It establishes immutable/controlled domain primitives and minimal invariant-only catalogs. It does not implement recall, history, reasoning, persistence, or player-action flow.

## Must do

- Represent Identity Nodes with `NodeId`, name, Identity kind, and description.
- Identity kinds in this slice are exactly Entity, Place, and Describer.
- Keep Identity independent from mutable relationships. An Entity does not own location/faction/etc.
- Represent Relationship Types as intentional controlled vocabulary.
- Represent Associations as addressable directed `(source, relationship, target)` assertions.
- Permit multiple distinct Relationship Types between the same endpoint Nodes.
- Reject unknown Association endpoints in the invariant catalog.
- Reject unapproved Relationship Types in the invariant catalog.
- Handle exact semantic Association duplicates deterministically without multiplying the same assertion.
- Keep `WorldTime` and `SystemTime` separate, strongly typed, immutable, non-negative coordinates.
- Provide immutable `ChronoStamp(world_time, system_time)`.
- Provide stable type-specific IDs. Do not introduce a universal graph-object ID in this slice.
- Preserve a clean public `chronospear.cam` API.

## Must not do

- No Historical Occurrence implementation.
- No Amend/Void implementation.
- No historical support graph.
- No lifecycle FUTURE/EFFECTIVE/ENDED resolution.
- No Perspective / KNOWS.
- No Language Surface implementation.
- No Groq or other LLM integration.
- No Action Reasoning Session.
- No Memory Creation Protocol.
- No Interaction/Chat Log.
- No Cleaner or Audit implementation.
- No Calendar implementation.
- No SQLite/database persistence.
- No semantic selector, embeddings, GraphRAG, or graph traversal.
- No UI/API server.
- No generic `Node` superclass that flattens future graph families.

## Invariants

1. Identity != occurrence.
2. Association != identity.
3. Relationship Type != identity/node.
4. Language Surface != truth (reserved for later).
5. Calendar concept != WorldTime (reserved for later).
6. Audit != world History (reserved for later).
7. WT != ST even when their numeric values happen to match.
8. ChronoStamp captures coordinates; it does not own or advance the authoritative clocks.
9. Node descriptions must not be used to smuggle mutable/secret/perspective facts. This is partly a semantic/code-review invariant, not something a validator can fully prove.
10. Legacy `Entity.place` is explicitly rejected as a CAM foundation assumption.

## Acceptance behavior

The test suite must prove:

- Node/Association IDs reject blanks and generated IDs are unique.
- Identity Nodes validate names and preserve the three locked Identity families.
- Identity Node records are immutable in Slice 1.
- Node ID conflicts are rejected.
- Relationship Types require canonical `UPPER_SNAKE_CASE` names.
- Unknown Relationship Types are not accepted by the vocabulary.
- Conflicting redefinitions of an existing Relationship Type are rejected.
- Associations preserve directionality.
- Two different relationship semantics can connect the same Nodes.
- Unknown source/target Nodes are rejected by the Association catalog.
- Unapproved relationship semantics are rejected by the Association catalog.
- A duplicate semantic assertion is not duplicated in memory merely because a new Association ID was proposed.
- One Association ID cannot identify two conflicting assertions.
- WorldTime and SystemTime remain distinct types.
- Both time coordinates are immutable and non-negative.
- ChronoStamp contains one WT and one ST and is immutable.

## Taxation

No general taxation framework is implemented in Slice 1. The catalogs intentionally use indexed dictionaries/sets so basic add/get validation is local. Later slices will expose query/recall taxation where it becomes meaningful.

## Done when

- `pytest` passes.
- `ruff check .` passes.
- `mypy` passes in strict mode.
- The code obeys `AGENTS.md`.
- No out-of-scope system has been scaffolded into an accidental architecture commitment.
