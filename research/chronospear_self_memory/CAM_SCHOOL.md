# CAM School A/B Experiment

Research-only experiment on `research/chronospear-self-memory`.

## Hypothesis

A general-purpose LLM may fail CAM evidence-sufficiency decisions because it has not learned how to navigate an external bounded memory system. A small synthetic curriculum that teaches CAM control habits may improve evidence discipline without increasing Packet #1 or making CAM reason about relevance.

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

## Curriculum goals

The fictional examples teach the model to:

1. distinguish topic-adjacent evidence from direct support;
2. request more bounded memory when the current evidence does not establish the claim;
3. preserve `HYPOTHESIS`, `UNRESOLVED`, and `EXPERIMENTALLY_PROVEN` labels;
4. use `AND` for independent current-surface requests;
5. avoid dependent `ACTIVATE X AND EXPAND X ...` scripts;
6. prefer another CAM request over an unsupported inference.

The curriculum intentionally does not contain ChronoSpear benchmark evidence IDs or benchmark answers.

## First targeted probes

These questions previously exposed premature evidence sufficiency / state-label problems:

```bash
python auto_handshake_school.py --question "What semantic risk did the Expansion experiment expose?"
python auto_handshake_school.py --question "How is our thinking about Expansion changing on 8/31?"
```

Useful behavior to watch:

- Does the model continue `EXPAND Expansion HISTORY` after seeing only the widening occurrence?
- Does it wait for the semantic-overreach occurrence before answering the risk question?
- Does it preserve hypothesis language rather than phrasing a proposed memory-map direction as an implemented policy change?
- Does it still use `AND` efficiently?

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
- throttle wait separately.

The school runner prints `curriculum_characters` and notes that provider prompt-token totals include the school prompt while CAM packet estimates do not.

## Interpretation

A positive result would not prove that model fine-tuning is required. It would support the narrower hypothesis that learned CAM-navigation behavior improves bounded-memory reasoning. If a small few-shot curriculum materially improves evidence discipline, a synthetic CAM interaction dataset and later fine-tuning become more justified experiments.
