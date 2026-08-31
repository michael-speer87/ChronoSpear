# Research Experiment: Minimum Viable First Packet

**Date:** 2026-08-31  
**Status:** Research only. Not production architecture.  
**Production code touched:** none.

## Question

Can ChronoSpear begin an LLM reasoning call with a small deterministic memory packet built from already-activated CAM objects, without making the packet builder semantically understand the player's question?

## Hypothesis

For the same activated CAM object(s), Packet #1 can be selected mechanically with fixed budgets. The LLM receives the latest interaction plus that small memory neighborhood and either:

1. answers from the supplied evidence, or
2. requests additional memory in ordinary language.

The packet builder should not decide that `where` means location, that `member` means `MEMBER_OF`, or otherwise choose memory based on question semantics.

## Deliberate boundary

The experiment begins **after object activation**. It does not test Language Surface recognition yet.

Inputs are:

- latest interaction;
- perspective label;
- already-activated object(s);
- a local ordered chat window;
- a local ordered history window;
- a local ordered effective-association window.

The builder applies only fixed tail budgets.

## First falsification probe

Build Packet #1 twice around the same activated object `Alric`:

- `Where is Alric?`
- `Who does Alric work for?`

The selected memory sections must be identical. Only the latest-interaction text may differ.

If the memory selection changes because of question wording, the builder is doing semantic reasoning and the hypothesis fails.

## Expansion probe

A minimal two-call harness accepts one of two model decisions:

- `ANSWER`
- `REQUEST_MORE` with a natural-language request

If the model requests more, the harness asks an expansion provider for bounded additional memory and sends one follow-up packet.

The current `ScriptedProvider` is deliberately not treated as LLM evidence. It only proves the control flow can be tested without a network/provider dependency. A real-model run is the next stage.

## Taxation captured

Packet #1 records:

- activated objects;
- chat items;
- history items;
- association items;
- rendered characters;
- approximate tokens (`ceil(characters / 4)`).

The token count is intentionally labeled an estimate because the research harness has no tokenizer dependency.

## Run locally

From this directory:

```bash
python -m unittest -v test_experiment.py
```

## What this experiment does not decide

- ideal packet budgets;
- Language Surface design;
- semantic expansion routing;
- perspective implementation;
- Historical Occurrence implementation;
- Groq/provider production integration;
- MCP write contract;
- whether the LLM's natural-language expansion requests are consistently useful.

Those remain experiment questions.
