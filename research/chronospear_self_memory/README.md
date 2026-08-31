# ChronoSpear Self-Memory Design Quest

Research-only dogfooding experiment. It is intentionally outside `src/chronospear` and does not change Production Slice 1.

## Purpose

Use a tiny CAM-shaped memory of ChronoSpear's own architecture to test whether bounded recall can help us answer design questions without repeatedly rediscovering old decisions.

The seed currently draws from:

- the 2026-08-26 CAM architecture handoff;
- the 2026-08-30 EOD handoff;
- the 2026-08-31 minimum-first-packet live probes and discussion.

The seed is curated research data, not a replacement for the authoritative source documents.

## Manual playground

`playground.py` lets a human act as the reasoner instead of immediately handing control to an LLM.

Packet #1 is intentionally synopsis-only. It exposes a memory-availability map but no Associations or Historical Occurrences. You decide which surfaced concept to expand, and each expansion returns only a bounded delta.

```bash
cd research/chronospear_self_memory
python playground.py
```

Useful commands inside the playground:

```text
expand <concept>   reveal the next bounded delta for a surfaced concept
map                show the current memory availability map
surfaced           list concepts currently available for expansion
admitted           inspect everything already admitted to this reasoning session
packet             reprint the most recent CAM delta
new                start a fresh question/session
help               show commands
quit               exit
```

The playground makes no LLM calls. It exists so the architecture can be explored directly before comparing human navigation with model navigation.

## Experimental rules

- Current associative statements carry explicit confidence/state labels.
- Immutable design occurrences preserve how the architecture changed.
- Literal concept-name/alias recognition is the only language activation used by this harness.
- The automated live quest sends synopses, a tiny fixed evidence budget, and a memory-availability map in Packet #1.
- The manual playground uses an even smaller synopsis-only Packet #1 so expansion behavior is visible.
- Expanding a surfaced concept sends its full Description at most once plus another tiny evidence page.
- Every later CAM packet is a delta: previously admitted synopses/descriptions/associations/history are removed from the new packet, not from CAM.
- The LLM must cite evidence IDs with its answer in the automated live quest.
- A right-sounding answer with unsupported evidence counts as a failure worth investigating.

## Offline tests

```bash
cd research/chronospear_self_memory
python -m unittest -v test_memory.py test_playground.py
```

## Live quest with Groq

Uses the same environment variables as the earlier packet probes:

```bash
export CS_DESIGN_PROVIDER=groq
python live_quest.py
```

Requires `GROQ_API_KEY` and `GROQ_MODEL`.

## Live quest with local Ollama

```bash
ollama run qwen2.5-coder:7b
```

After the model is present, the quest can use Ollama's local API:

```bash
export CS_DESIGN_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5-coder:7b
python live_quest.py
```

## What to watch

The benchmark is deliberately small and human-checkable. Useful failure classes include:

- stale/historical ideas leaking into a current answer;
- hypotheses being presented as locked architecture;
- correct prose supported by the wrong evidence;
- excessive expansion rounds;
- requests for unsurfaced concepts;
- token growth caused by repeated memory rather than genuinely new evidence.
