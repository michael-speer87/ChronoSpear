# CAM School A/B Experiment

Research-only experiment on `research/chronospear-self-memory`.

## Hypothesis

A general-purpose LLM may fail CAM evidence-sufficiency decisions because it has not learned how to navigate an external bounded memory system. A synthetic curriculum that teaches CAM control habits may improve evidence discipline without increasing Packet #1 or making CAM reason about relevance.

This is a prompt-level precursor to any future fine-tuning experiment. It does not train model weights.

## Control and intervention

Control:

```bash
python auto_handshake_resilient.py
```

Intervention:

```bash
python auto_handshake_school.py
```

Both use the same:

- CAM seed;
- Packet #1 behavior;
- page sizes and memory budgets;
- protocol parser;
- AND semantics;
- rate-limit retry behavior;
- benchmark questions;
- model/provider configuration.

The intervention adds only a synthetic few-shot curriculum to the LLM system prompt.

## CAM School v1 observation

The first curriculum taught the model to keep retrieving when current evidence was merely related to the question.

That produced a useful split result:

- On `What semantic risk did the Expansion experiment expose?`, the schooled model continued to a second Expansion History page and answered with the directly supporting `o-0831-overreach` occurrence instead of stopping on adjacent widening evidence.
- On `How is our thinking about Expansion changing on 8/31?`, the model overcorrected. It made 13 History requests across five LLM calls, branched into several surfaced concepts, and consumed substantially more provider context before answering.

The v1 lesson therefore appears to have improved persistence but not termination. It taught something close to `more memory may help -> keep looking`, which is too broad.

## CAM School v2 hypothesis

The model needs to judge evidence sufficiency from the content already admitted, not from the mere existence of additional memory.

Before every response, it should silently classify its evidence state:

- `INSUFFICIENT`: the material answer cannot yet be supported;
- `PARTIAL`: some material claims are supported but an important claim is missing;
- `SUFFICIENT`: every material claim the model intends to state is supported at the strength it intends to state it.

These are reasoning habits only. They are not new CAM commands and must never appear in protocol output.

V2 retrieval policy:

1. If evidence is sufficient, answer immediately even when additional CAM memory remains available.
2. If evidence is insufficient or partial, identify the specific unsupported material claim.
3. Request only the smallest currently valid CAM channel likely to resolve that missing claim.
4. Topic-adjacent evidence is not direct support and must not be strengthened into a missing premise.
5. Stop as soon as the material uncertainty is resolved. Do not exhaust memory for completeness.
6. Stay on the directly relevant concept unless admitted evidence identifies another concept needed to resolve the missing fact, or the relevant channel is exhausted.
7. Preserve `HYPOTHESIS`, `UNRESOLVED`, and `EXPERIMENTALLY_PROVEN` labels exactly.
8. Use `AND` only when multiple independent facts are genuinely missing now, not merely because multiple commands are available.

The curriculum intentionally uses fictional entities and synthetic evidence IDs. It contains no ChronoSpear benchmark evidence IDs or benchmark answers.

## CAM School v2 protocol-leak observation

The first V2 live probes failed before CAM retrieval because the model exposed the private sufficiency checklist in its visible response:

```text
What material claim can I not support yet?
EXPAND Expansion HISTORY
```

The selected CAM operation was plausible, but the extra self-question violated the deliberately strict external protocol. This is classified as a protocol-leak failure, not evidence-selection failure.

V2.1 therefore keeps the same sufficiency policy but adds a highest-priority output contract:

- sufficiency classification and missing-fact identification are private reasoning only;
- never emit `INSUFFICIENT`, `PARTIAL`, `SUFFICIENT`, a self-question, rationale, or commentary;
- the entire visible response must be exactly one valid CAM command/batch or the two-line `ANSWER` / `EVIDENCE` form;
- the protocol parser remains strict so future leakage stays observable rather than being silently repaired by the harness.

## Targeted probes

Run:

```bash
python auto_handshake_school.py --question "What semantic risk did the Expansion experiment expose?"
python auto_handshake_school.py --question "How is our thinking about Expansion changing on 8/31?"
```

For the semantic-risk question, desired behavior is:

- reject merely adjacent widening evidence as insufficient;
- retrieve until the semantic-overreach evidence appears;
- stop immediately once that evidence directly supports the answer;
- expose no private sufficiency reasoning in protocol output.

For the 8/31-changing question, desired behavior is:

- retrieve enough evidence to distinguish observed widening/overreach behavior from later hypotheses;
- preserve hypothesis language rather than upgrading it into a locked change;
- avoid broad repeated History sweeps across every surfaced concept;
- stop once the requested current state of thinking can be stated at the correct evidence strength;
- expose no private sufficiency reasoning in protocol output.

## Full A/B metrics

Compare at minimum:

- answer completion rate;
- expected-support hits, with human review of `EVIDENCE:none` cases;
- evidence/state-label correctness;
- average LLM calls per question;
- `AND_BATCH` use;
- provider prompt tokens;
- provider total tokens;
- CAM packet estimated tokens;
- CAM operation time;
- active provider time;
- throttle wait separately;
- redundant retrievals after sufficient evidence was already admitted;
- unnecessary branching into adjacent surfaced concepts;
- protocol leakage of private sufficiency reasoning.

The school runner prints `curriculum_characters` and notes that provider prompt-token totals include the school prompt while CAM packet estimates do not.

## Interpretation

A positive V2.1 result would not prove that model fine-tuning is required. It would support the narrower hypothesis that learned evidence-sufficiency and selective-navigation behavior improves bounded-memory reasoning while remaining compatible with a tiny deterministic external protocol.

The strongest signal would be a middle path between the observed extremes:

```text
unschooled: related evidence -> answer too early
v1 school: more memory exists -> retrieve too much
v2: private reasoning leaked into protocol output
v2.1 target: unsupported material claim -> retrieve narrowly -> direct support -> stop -> emit only protocol
```

If a synthetic curriculum consistently moves the model toward that middle path, a CAM interaction dataset and later fine-tuning become much more justified experiments.
