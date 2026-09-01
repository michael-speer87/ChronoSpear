# CAM-Native V1.1 LoRA Training on Kaggle

Fallback GPU workflow for training the CAM-native Qwen3-0.6B V1.1 LoRA adapter when Colab runtime allocation is unavailable.

## Goal

Train the V1.1 adapter on Kaggle GPU while preserving the same experiment controls used for V1:

- base model: `Qwen/Qwen3-0.6B`
- epochs: 3
- learning rate: `1e-4`
- LoRA rank: 16
- target modules: all linear layers
- assistant-only loss
- V1.1 data: 816 train / 232 eval
- runtime CAM system prompt remains 813 characters

Only the training curriculum changes: V1.1 adds the small CAM ontology-literacy supplement.

## Local machine: prepare upload bundle

From `research/chronospear_self_memory`:

```bash
rm -f cam_native_training_bundle_v11.zip
zip -r cam_native_training_bundle_v11.zip \
  cam_native_train.py \
  requirements-cam-native.txt \
  cam_native_data_v11/train.jsonl \
  cam_native_data_v11/eval.jsonl
```

## Kaggle: create notebook and enable GPU

Create a new Kaggle Notebook.

In the notebook Settings / Session options:

1. Set **Accelerator** to **GPU**.
2. Turn **Internet** on for the interactive session. Internet is needed for pip and Hugging Face model download.
3. Start/restart the session if Kaggle requests it.

Verify CUDA before doing anything else:

```python
import torch
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO CUDA GPU")
```

Stop if CUDA is `False`. Do not use `--allow-cpu` on Kaggle.

## Kaggle: upload the V1.1 bundle

Use the Notebook editor **Input -> Upload** button and upload `cam_native_training_bundle_v11.zip`.

Kaggle exposes uploaded input data under `/kaggle/input/...` and may unpack ZIP contents automatically. Locate the trainer with:

```python
from pathlib import Path

matches = list(Path("/kaggle/input").rglob("cam_native_train.py"))
print(matches)
assert matches, "cam_native_train.py was not found under /kaggle/input"
WORK = matches[0].parent
print("WORK=", WORK)
```

Switch into the uploaded bundle directory:

```python
import os
os.chdir(WORK)
print(os.getcwd())
```

Confirm the V1.1 files are present:

```python
from pathlib import Path
for path in [
    Path("cam_native_train.py"),
    Path("requirements-cam-native.txt"),
    Path("cam_native_data_v11/train.jsonl"),
    Path("cam_native_data_v11/eval.jsonl"),
]:
    print(path, path.exists())
```

All four should print `True`.

## Install dependencies

With Internet enabled:

```bash
!python -m pip install -q -r requirements-cam-native.txt
!python -m pip uninstall -y torchao
```

The CAM-native experiment does not use torchao. Removing Kaggle's optional/stale package avoids the same PEFT injection problem encountered in Colab.

## Smoke training

Run the 20-optimizer-step smoke test first:

```bash
!python cam_native_train.py \
  --train cam_native_data_v11/train.jsonl \
  --eval cam_native_data_v11/eval.jsonl \
  --output-dir /kaggle/working/cam_native_adapter_v11_smoke \
  --smoke
```

Expected header includes:

```text
CAM-NATIVE LORA TRAINING
model=Qwen/Qwen3-0.6B
train_examples=816
eval_examples=232
cuda=True
mode=SMOKE (20 optimizer steps)
```

Stop if CUDA is false or if the smoke run fails.

## Full V1.1 training

Once smoke succeeds:

```bash
!python cam_native_train.py \
  --train cam_native_data_v11/train.jsonl \
  --eval cam_native_data_v11/eval.jsonl \
  --output-dir /kaggle/working/cam_native_adapter_qwen3_0_6b_v11
```

Do not change the training hyperparameters for the first V1 vs V1.1 comparison.

## Package the adapter

After training completes:

```bash
%cd /kaggle/working
!zip -r cam_native_adapter_qwen3_0_6b_v11.zip cam_native_adapter_qwen3_0_6b_v11
!ls -lh cam_native_adapter_qwen3_0_6b_v11.zip
```

Download `cam_native_adapter_qwen3_0_6b_v11.zip` from the Notebook Output / working files area.

## Local next step

Bring the adapter back to `research/chronospear_self_memory`, unzip it, convert the LoRA to GGUF with llama.cpp's `convert_lora_to_gguf.py`, then run the same Mini-Igor handshake benchmarks with the 813-character runtime prompt and rich initial packet.

The first discriminating benchmark remains:

```text
What evidence do we have that Packet #1 can stay question-agnostic?
```

The experiment asks whether learned CAM ontology changes evidence selection while preserving the V1 behavioral fingerprint.
