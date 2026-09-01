# Architecture Boundaries for Codex

## The current machine shape

This is the intended runtime heartbeat. Most of it is **future slices**, but Slice 1 must not make it impossible.

```text
PLAYER ACTION
    |
    v
Interaction Log (raw action/conversation, future)
    |
    v
CAM bounded recall
    ^
    | controlled language requests
    v
Fresh per-action LLM reasoning session
    |
    v
LLM RESULT (not truth yet)
    |
    v
Memory Creation Protocol
    |-- resolve/create identities
    |-- create immutable Historical Occurrence
    |-- create/end/reconstruct Associations as justified
    |-- apply perspective knowledge consequences
    `-- cleanup/Audit when appropriate
    |
    v
CAM is authoritative for the next action
```

## Boundary: CAM vs LLM

- CAM remembers and retrieves.
- LLM reasons/interprets/narrates from bounded evidence.
- LLM may request additional context in ordinary language through controlled Language Surfaces.
- CAM decides traversal, permissions, semantic targets, and budgets.
- LLM never receives direct unrestricted graph mutation/traversal authority.
- Every player action starts a fresh provider conversation.

## Boundary: History vs Association

- History answers **what happened** and persists.
- Association answers **what meaning/connection is useful now** and is plastic.
- An Association may be supported by multiple Historical Occurrences.
- Pruning reconstructable green memory does not delete blue History.

## Boundary: Interaction Log vs History

- Interaction Log answers **what was said/submitted**.
- History answers **what happened in-world**.
- A player's statement may be stored in the Interaction Log without becoming world truth.
- Future LLM sessions may receive a bounded recent Interaction Log window ordered by SystemTime.

## Boundary: campaign save format vs runtime CAM

ChronoSpear campaigns are intended to have a human-editable JSON representation.

The JSON campaign file is the portable save/interchange representation of a world, not the runtime CAM object model itself.

Rules for the eventual storage layer:

- Save/load must preserve stable Identity, Association, Occurrence, and temporal identifiers rather than regenerating them.
- Loading JSON must validate the same CAM invariants enforced by the runtime catalogs; editable does not mean blindly trusted.
- Broken references, invalid Relationship Types, invalid Historical Occurrence participants, or invalid Places must fail with useful validation errors rather than silently damaging the graph.
- A future CAM world editor/controller should read and write the same campaign representation so DMs do not need to understand CAM internals to author worlds.
- Advanced users may intentionally edit campaign JSON directly or generate it with external tooling.
- Campaign-preparation tooling may rewrite seeded world history before play. Runtime ChronoSpear should still treat admitted Historical Occurrences as immutable during normal play unless a future explicit correction mechanism such as VARA applies.
- The public campaign format should remain clearer and more stable than whatever internal indexes CAM eventually uses for efficient runtime retrieval.

No JSON persistence implementation is part of Slice 1 or Slice 2.

## Boundary: time

There are two coordinates:

- `WorldTime`: world chronology.
- `SystemTime`: ChronoSpear acquisition/revision chronology.

`ChronoStamp` captures both at a boundary.

Rules:

- No generic ambiguous `tick: int` in new domain records when the meaning is WT/ST.
- Do not infer that ST is the same as same-WT occurrence sequence; backfilled historical knowledge can have old WT and new ST.
- Do not create a Calendar mega-object inside WorldTime.
- Do not turn ChronoStamp into mutable current clock state.
- Equal WT/ST coordinate values appearing in multiple historical stamps are not competing truths; competing mutable clock authorities are the thing to prevent.
- Clock ownership/advancement orchestration is intentionally a later slice.

## Boundary: Node descriptions

Descriptions provide identity clarification only.

Good:

`The Meridian — A scholarly organization that charts celestial routes.`

Bad:

`Oris Vale — Secretly the wizard everyone is hunting.`

The bad fact is mutable/secret/perspective-sensitive and belongs in Association/History.

## Boundary: legacy code

The legacy DungeonMind Python repository is reference material only.

Safe idea to transplant:

- immutable non-negative WorldTime value object;
- strong validation/testing discipline.

Unsafe assumption to transplant:

- `Entity.place` ownership. In CAM, `Alric --LIVES_IN--> Stonebridge` or another controlled Association carries location meaning.

Do not preserve legacy class shapes merely to reduce rewrite work.
