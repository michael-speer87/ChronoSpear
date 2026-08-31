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

`wiretap_playground.py` exposes the conversation between CAM and the LLM one hop at a time. It is intentionally human-gated: CAM never calls the provider automatically, and a model memory request never executes automatically.

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
  -> human chooses whether to execute the requested CAM command(s)
  -> CAM builds a new bounded delta
  -> human inspects delta
  -> send
  -> repeat
```

### Tiny LLM -> CAM protocol

The LLM is not allowed to request memory in ordinary language. It has only these controls:

```text
ACTIVATE <exact concept name or alias>
EXPAND <surfaced concept> DESCRIPTION
EXPAND <surfaced concept> ASSOCIATIONS
EXPAND <surfaced concept> HISTORY

<command> AND <command> [AND <command> ...]

ANSWER: <answer>
EVIDENCE: <ids or none>
```

`ACTIVATE` performs strict identity activation. It does not fuzzy-match or guess.

`EXPAND` is channel-specific. CAM does not infer why the channel was requested:

- `DESCRIPTION` returns the full stable identity Description if it has not already been admitted.
- `ASSOCIATIONS` returns the next bounded Association page only.
- `HISTORY` returns the next bounded Historical Occurrence page only.

`AND` joins up to four independent memory commands into one LLM turn. Example:

```text
EXPAND Identity Node DESCRIPTION AND EXPAND Relationship Type DESCRIPTION
```

Every command in an `AND` chain is validated against the same pre-command control surface before any operation executes. `AND` is parallel request glue, not a scripting language. Therefore this is intentionally invalid:

```text
ACTIVATE Stonebridge AND EXPAND Stonebridge HISTORY
```

The second command becomes valid only after the first command changes CAM state, so it requires another reasoning turn.

A response such as `tell me more about Expansion` or the older `REQUEST_MORE: Expansion` is a protocol violation. The wiretap reports it and executes nothing.

Useful wiretap commands mirror the single-operation protocol so the human can inspect and manually reproduce what the LLM requested:

```text
send                                  send only the pending CAM delta to the LLM
response                              reprint the latest raw LLM response
conversation                          show the full provider message transcript
packet                                inspect the current/pending CAM delta
map                                   inspect the current memory availability map
surfaced                              list currently surfaced concepts
admitted                              show memory CAM has already admitted this session
activate <exact concept>              manually execute exact activation
expand <concept> DESCRIPTION          manually request Description only
expand <concept> ASSOCIATIONS         manually request the next Association page
expand <concept> HISTORY              manually request the next History page
protocol                              reprint the allowed LLM -> CAM vocabulary
memory ...                            use the same mutable memory interface as playground.py
new                                   fresh question while keeping memory edits
help
quit
```

The provider response is parsed only for visibility. A valid `AND` chain is displayed operation-by-operation but is never auto-executed in wiretap mode.

This is intentionally a memory-management protocol, not a query language. It contains no `FIND_RELEVANT`, `FIND_LOCATION`, semantic filters, or inference commands.

## Autonomous CAM ↔ LLM handshake benchmark

`auto_handshake.py` removes the human gate while keeping the same protocol and deterministic CAM operations. A valid `ACTIVATE`, `EXPAND`, or bounded `AND` response is executed immediately, the resulting CAM delta is appended to the same reasoning conversation, and the loop continues until `ANSWER`, failure, or the round limit.

`AND` batches are validated atomically against the current control surface. If one command is invalid, the whole batch fails before CAM performs any of its operations. Valid batch results are merged into one outgoing CAM delta.

Run the seeded nine-question design suite:

```bash
cd research/chronospear_self_memory
export CS_DESIGN_PROVIDER=groq
python auto_handshake.py
```

Run one custom question:

```bash
python auto_handshake.py --question "What semantic risk did Expansion expose?"
```

For Groq rate-limit-aware runs:

```bash
python auto_handshake_resilient.py
```

Useful options:

```text
--max-rounds N   maximum LLM calls per question; default 10
--quiet          suppress per-round trace and print only aggregate results
```

The benchmark records:

- end-to-end wall time per question;
- provider latency per LLM call;
- CAM build/operation time separately from provider time;
- number of LLM calls per question;
- counts of ACTIVATE, channel-specific EXPAND, and AND_BATCH operations;
- CAM packet token estimates;
- numeric provider usage totals returned by Groq/Ollama;
- final evidence IDs and expected-support hits for the seeded quest.

Protocol violations and invalid CAM operations fail explicitly. The autonomous loop does not interpret or repair an invented command.

## Experimental rules

- Current associative statements carry explicit confidence/state labels.
- Immutable design occurrences preserve how the architecture changed.
- Literal concept-name/alias recognition is the only language activation used by this harness.
- Unknown or misspelled Concept names do not fuzzy-match; strict activation is intentional for the current experiment.
- The automated live quest sends synopses, a tiny fixed evidence budget, and a memory-availability map in Packet #1.
- The manual, wiretap, and autonomous handshake modes use a synopsis-only Packet #1 so expansion behavior is visible.
- Generic manual playground expansion still returns a tiny mixed bundle for the older human-only experiment.
- Wiretap/autonomous expansion is channel-specific: Description, Associations, or History only.
- `AND` may combine up to four independent current-surface memory operations in one LLM turn.
- `AND` cannot express dependent multi-step navigation; commands are validated against one unchanged pre-batch surface.
- Every later CAM packet is a delta: previously admitted synopses/descriptions/associations/history are removed from the new packet, not from CAM.
- Manual memory mutation never silently cascades Concept deletion into Associations or Historical Occurrences.
- The wiretap LLM can request CAM operations but cannot execute them; autonomous mode executes only valid protocol operations.
- CAM protocol verbs describe memory operations, never semantic goals.
- A right-sounding answer with unsupported evidence counts as a failure worth investigating.

## Offline tests

```bash
cd research/chronospear_self_memory
python -m unittest -v test_memory.py test_playground.py test_memory_interface.py test_wiretap_playground.py test_auto_handshake.py test_auto_handshake_resilient.py
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

The same provider variables work with `wiretap_playground.py`, `auto_handshake.py`, and `auto_handshake_resilient.py`.

## What to watch

The benchmark and playgrounds are deliberately small and human-checkable. Useful failure classes include:

- stale/historical ideas leaking into a current answer;
- hypotheses being presented as locked architecture;
- correct prose supported by the wrong evidence;
- excessive expansion rounds;
- whether AND reduces LLM round trips without causing packet bloat;
- requests for unsurfaced concepts;
- requests for an unavailable or already exhausted channel;
- dependent commands incorrectly attempted inside an AND batch;
- protocol violations where the LLM invents its own CAM language;
- whether the LLM can repair a missed/misspelled explicit object without CAM guessing;
- token growth caused by repeated memory rather than genuinely new evidence;
- how much latency belongs to CAM versus the provider/model;
- dangling references or packet failures caused by destructive manual memory edits;
- differences between the memory path a human chooses and the path the LLM requests.
