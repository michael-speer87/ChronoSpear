# Codex Handoff After Slice 1

## What you are receiving

A deliberately small greenfield ChronoSpear repository containing Production Slice 1: CAM Core Primitives.

The repository already includes the architecture constitution and known future graph/memory object taxonomy. Treat those documents as constraints, not suggestions.

## Your immediate job when this repository is handed to you

1. Read `AGENTS.md`.
2. Read every file in `docs/`.
3. Run:
   - `pytest`
   - `ruff check .`
   - `mypy`
4. Report any mismatch between implementation and the Slice 1 contract before changing architecture.
5. Do **not** begin Slice 2 until a new explicit Slice 2 handoff is supplied.

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
- HistoricalOccurrence classes;
- speculative factories/managers for future systems.

The smallness is intentional.

## Known next direction, not authorization

The likely next slice will involve immutable historical occurrence representation and its relationship to Identity/ChronoStamp, but that architecture must be discussed/refined first. This sentence is context only, not permission to implement it.
