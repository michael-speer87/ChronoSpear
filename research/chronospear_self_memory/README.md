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
expand <concept>              reveal the next bounded delta for a surfaced concept
map                           show the current memory availability map
surfaced                      list concepts currently available for expansion
admitted                      inspect everything already admitted to this reasoning session
packet                        reprint the most recent CAM delta
memory                        show the memory-interface commands
memory summary                count stored Concepts, Associations, and Occurrences
memory concepts               list all stored Concepts
memory associations           list all stored Associations
memory history                list all stored Historical Occurrences
memory show <concept>         inspect one Concept
memory add concept            interactively add a Concept
memory add association        interactively add an Association
memory add occurrence         interactively add a Historical Occurrence
memory remove concept <name>  remove only the Concept; references are not cascaded
memory remove association <id>
memory remove occurrence <id>
memory integrity              report dangling Concept references
memory reset                  discard all playground edits and reload the clean seed
new                           start a fresh question/session while keeping memory edits
help                          show commands
quit                          exit
```

Memory edits are session-local to the running playground. They never rewrite `seed.py`. Concept removal is intentionally non-cascading so broken references remain observable. `memory reset` restores a clean seed and discards the current reasoning session.

The playground makes no LLM calls. It exists so the architecture can be explored directly before comparing human navigation with model navigation.

## Human-intercepted CAM ↔ LLM wiretap

`wiretap_playground.py` exposes the conversation between CAM and the LLM one hop at a time. It is intentionally human-gated: CAM never calls the provider automatically, and a model `REQUEST_MORE` response never executes a memory action automatically.

```bash
cd research/chronospear_self_memory
export CS_DESIGN_PROVIDER=groq
python wiretap_playground.py
```

The intended loop is:

```text
question
  -> CAM builds Packet #1
  -> human inspects packet
  -> send
  -> human inspects raw LLM response
  -> human chooses expand/activate/ignore
  -> CAM builds a new delta
  -> human inspects delta
  -> send
  -> repeat
```

Useful wiretap commands:

```text
send                        send only the pending CAM delta to the LLM
response                    reprint the latest raw LLM response
conversation                show the full provider message transcript
packet                      inspect the current/pending CAM delta
map                         inspect the current memory availability map
surfaced                    list currently surfaced concepts
admitted                    show memory CAM has already admitted this session
expand <concept>            manually execute bounded expansion
activate <exact concept>    manually surface an exact stored concept/alias
memory ...                  use the same mutable memory interface as playground.py
new                         fresh question while keeping memory edits
help
quit
```

`activate` is deliberately strict. A stored exact name or alias can be surfaced; a misspelling such as `Historical Occurence` is not fuzzy-corrected. This lets the human observe whether the LLM repairs language errors from context and explicitly asks for the correct object.

The provider response is parsed only for visibility. Even a valid `REQUEST_MORE: Expansion` prints as `PARSED ONLY, NOT EXECUTED`; the human must decide whether to run `expand Expansion`.

## Experimental rules

- Current associative statements carry explicit confidence/state labels.
- Immutable design occurrences preserve how the architecture changed.
- Literal concept-name/alias recognition is the only language activation used by this harness.
- Unknown or misspelled Concept names do not fuzzy-match; strict activation is intentional for the current experiment.
- The automated live quest sends synopses, a tiny fixed evidence budget, and a memory-availability map in Packet #1.
- The manual and wiretap playgrounds use an even smaller synopsis-only Packet #1 so expansion behavior is visible.
- Expanding a surfaced concept sends its full Description at most once plus another tiny evidence page.
- Every later CAM packet is a delta: previously admitted synopses/descriptions/associations/history are removed from the new packet, not from CAM.
- Manual memory mutation never silently cascades Concept deletion into Associations or Historical Occurrences.
- The wiretap LLM can request memory but cannot execute CAM actions.
- The LLM must cite evidence IDs with its answer in the automated live quest.
- A right-sounding answer with unsupported evidence counts as a failure worth investigating.

## Offline tests

```bash
cd research/chronospear_self_memory
python -m unittest -v test_memory.py test_playground.py test_memory_interface.py test_wiretap_playground.py
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

The same provider variables work with `wiretap_playground.py`.

## What to watch

The benchmark and playgrounds are deliberately small and human-checkable. Useful failure classes include:

- stale/historical ideas leaking into a current answer;
- hypotheses being presented as locked architecture;
- correct prose supported by the wrong evidence;
- excessive expansion rounds;
- requests for unsurfaced concepts;
- whether the LLM can repair a missed/misspelled explicit object without CAM guessing;
- token growth caused by repeated memory rather than genuinely new evidence;
- dangling references or packet failures caused by destructive manual memory edits;
- differences between the memory path a human chooses and the path the LLM requests.
