# ChronoSpear

## CAM visual playground

Inspect the deterministic demo world in a local, read-only browser UI:

```bash
python -m chronospear.playground
```

Then open the printed address (by default `http://127.0.0.1:8000`). Use the two
selectors or the connected-object buttons to follow identities, associations, and
historical occurrences.

ChronoSpear is a historical reasoning brain built around **Chrono Associative Memory (CAM)**.

This repository seed contains **Production Slice 1: CAM Core Primitives**. It is intentionally small. It establishes the canonical vocabulary that later CAM slices must build upon without prematurely implementing History, perspective, Language Surfaces, LLM integration, persistence, or memory formation.

## Slice 1 implements

- `IdentityNode` with locked Identity families: Entity, Place, Describer;
- strongly typed `IdentityId` and `AssociationId`;
- controlled `RelationshipType` vocabulary;
- addressable directed `Association` assertions;
- minimal invariant-only catalogs used to validate IDs/endpoints/vocabulary;
- distinct immutable `WorldTime` and `SystemTime` coordinates;
- immutable `ChronoStamp(WorldTime, SystemTime)`.

## Slice 1 intentionally does not implement

Historical Occurrences, Amend/Void, historical supports, lifecycle episodes, Perspective/KNOWS, Language Surfaces, Groq/LLM behavior, Memory Creation Protocol, Interaction Log, Cleaner, Audit, Calendar, persistence, semantic retrieval, graph traversal, or UI.

Read `AGENTS.md` before changing architecture. Then read:

1. `docs/SLICE_1_CONTRACT.md`
2. `docs/GRAPH_OBJECT_TAXONOMY.md`
3. `docs/ARCHITECTURE_BOUNDARIES.md`
4. `docs/CODEX_NEXT_STEPS.md`

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy
```
