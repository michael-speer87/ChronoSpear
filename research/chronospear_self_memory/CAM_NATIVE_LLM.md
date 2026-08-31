# CAM-Native LLM Experiment

Research-only experiment on `research/chronospear-self-memory`.

## Hypothesis

A small model fine-tuned on CAM navigation behavior may use bounded external memory more reliably and with less repeated prompt instruction than a larger general-purpose model taught CAM behavior through a long few-shot system prompt.

This experiment does **not** train a model from scratch. It applies a LoRA adapter to `Qwen/Qwen3-0.6B` using supervised fine-tuning (SFT).

The intentionally tiny 0.6B base model is useful here: success would show that CAM interaction behavior can be learned by a small reasoner rather than requiring a large model plus a large instruction prompt.

## What is trained

The adapter is trained on behavior, not ChronoSpear lore.

Synthetic skills include:

- related evidence is not direct support;
- direct support means stop even when more memory exists;
- partial multi-claim answers retrieve the missing fact;
- `HYPOTHESIS` is not silently upgraded into an adopted decision;
- branch to another surfaced concept only when admitted evidence points there;
- use `AND` for genuinely independent missing facts;
- avoid unnecessary `AND` commands;
- use Description evidence without exhausting History;
- activate an explicit unsurfaced concept;
- emit only valid CAM protocol output.

The default dataset contains 11 behavior families × 64 training variants = 704 training examples, plus 11 × 16 = 176 held-out synthetic evaluation examples.

Training and evaluation name vocabularies are intentionally different, and the dataset builder rejects known ChronoSpear benchmark strings/evidence IDs.

## Compact native contract

The trained model receives a small system contract rather than CAM School's large curriculum. The goal is to move navigation/evidence-sufficiency behavior into adapter weights.

CAM itself is unchanged.

## Files

- `cam_native_dataset.py` builds synthetic train/eval JSONL.
- `cam_native_train.py` trains a LoRA adapter with TRL + PEFT.
- `cam_native_provider.py` loads the local base model and optional adapter.
- `cam_native_eval.py` scores held-out synthetic policy behavior.
- `cam_native_handshake.py` plugs the local model directly into the real ChronoSpear autonomous CAM benchmark.
- `test_cam_native_dataset.py` checks protocol validity, holdout separation, and benchmark contamination guards.
- `requirements-cam-native.txt` lists the isolated ML dependencies.

## Important hardware warning

**Do not start the real LoRA training on the Beelink CPU by accident.**

`cam_native_train.py` refuses CPU training unless `--allow-cpu` is explicitly supplied. Local 0.6B inference is reasonable on CPU; backpropagation is a different animal.

Use a CUDA environment for the real training run. A hosted notebook is fine because the output we need is only the resulting LoRA adapter directory.

If PyTorch/Transformers installation fails on a very new Python version, use a Python 3.11 or 3.12 virtual environment for this isolated ML experiment rather than changing the main ChronoSpear environment.

## Step 1: Build data and run offline guards

```bash
cd research/chronospear_self_memory
python -m unittest -v test_cam_native_dataset.py
python cam_native_dataset.py
```

Expected default counts:

```text
train_examples=704
eval_examples=176
skills=11
```

Inspect a few generated records if desired:

```bash
head -n 3 cam_native_data/train.jsonl
```

## Step 2: Create an isolated ML environment

Prefer a separate Python 3.11/3.12 environment so the research training stack does not disturb the normal project venv.

```bash
python3.11 -m venv .venv-cam-native
source .venv-cam-native/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-cam-native.txt
```

## Step 3: Baseline the untrained 0.6B model

This downloads the Qwen3-0.6B base model and evaluates it locally without any adapter.

```bash
python cam_native_eval.py --base-only
```

Useful metrics:

- protocol validity;
- decision-signature accuracy;
- exact-output accuracy;
- per-skill decision accuracy.

This is the tiny-potato control.

## Step 4: Smoke-test the training stack on CUDA

**Stop here if the machine has no CUDA GPU. Move the repository/data to a CUDA machine or hosted notebook instead.**

```bash
python cam_native_train.py --smoke
```

The smoke run performs only 20 optimizer steps. It verifies that Qwen, TRL, PEFT, the chat template, assistant-only loss, and LoRA all work together.

## Step 5: Train the first adapter

```bash
python cam_native_train.py
```

Defaults:

- base: `Qwen/Qwen3-0.6B`
- LoRA rank: 16
- target modules: all linear layers
- epochs: 3
- learning rate: `1e-4`
- assistant-only loss
- max sequence length: 1024

Output:

```text
cam_native_adapter_qwen3_0_6b/
```

This adapter directory is the artifact to copy back to the local ChronoSpear checkout if training happened elsewhere.

## Step 6: Held-out synthetic evaluation

```bash
python cam_native_eval.py
```

Compare against the base-only result from Step 3.

The first success criterion is not perfection. We want a large increase in:

- valid CAM protocol output;
- correct retrieve-vs-answer decisions;
- stopping when direct support is present;
- continued retrieval when evidence is only adjacent;
- preservation of hypothesis state.

## Step 7: Real ChronoSpear transfer test

First run the untrained tiny model against the real CAM benchmark:

```bash
python cam_native_handshake.py --base-only
```

Then run the trained adapter:

```bash
python cam_native_handshake.py
```

`cam_native_handshake.py` disables CAM School and replaces the long few-shot lesson with the compact CAM-native system contract. The underlying CAM seed, packets, budgets, protocol parser, AND semantics, and nine benchmark questions remain unchanged.

The strongest result would be:

```text
Qwen3-0.6B base        poor CAM behavior
Qwen3-0.6B + CAM LoRA  materially better CAM behavior
GPT-OSS + CAM School   comparable behavior but much larger prompt tax
```

## Key measurements

Record for all three configurations:

- answered / protocol failure / CAM-operation failure;
- expected-support hits plus human evidence review;
- LLM calls per question;
- unnecessary expansions after sufficient evidence;
- provider/local prompt tokens;
- completion tokens;
- CAM packet token estimates;
- answer/state-label correctness;
- active inference time.

The central question is not whether a 0.6B model is generally smarter than GPT-OSS. It obviously is not. The question is whether a tiny specialized reasoner can become **better at the narrow CAM interaction policy** than a much larger unspecialized model that has to be re-taught that policy in every prompt.
