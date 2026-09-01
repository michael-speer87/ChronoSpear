# Codex Handoff After Slice 2

## What you are receiving

A deliberately small ChronoSpear production CAM containing:

- Slice 1: CAM Core Primitives
- Slice 2: Immutable Historical Occurrences

The repository includes the architecture constitution, graph/memory taxonomy, and explicit slice contracts. Treat those documents as constraints, not suggestions.

## Your immediate job when this repository is handed to you

1. Read `AGENTS.md`.
2. Read every file in `docs/`.
3. Run:
   - `pytest`
   - `ruff check .`
   - `mypy`
4. Report any mismatch between implementation and the active Slice 2 contract before changing architecture.
5. Confirm Slice 1 behavior still passes unchanged.
6. Do **not** begin another production slice until a new explicit contract/handoff is supplied.

## What not to "improve" yet

Do not add:

- SQLAlchemy/SQLite repositories;
- graph database adapters;
- generic Node inheritance hierarchies;
- pydantic dependency;
- FastAPI;
- LLM/provider code;
- event sourcing framework;
- DI/service containers;
- Calendar models;
- Language Surface implementation;
- Amend/Void/VARA;
- Association lifecycle resolution;
- Association-to-History provenance/support;
- Perspective/KNOWS;
- recall or packet construction;
- speculative factories/managers for future systems.

The smallness is intentional.

## Next direction

Not yet authorized. Discuss and refine the next CAM production slice before implementation.
