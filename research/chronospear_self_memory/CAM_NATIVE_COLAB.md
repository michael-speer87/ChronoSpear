# CAM-Native LoRA Training on Google Colab

Research-only workflow for training the CAM-native Qwen3-0.6B LoRA adapter without training on the local Beelink.

## Goal

Train only the LoRA adapter on a hosted NVIDIA GPU, then bring the adapter directory back to the local ChronoSpear research checkout for evaluation.

The training bundle contains only synthetic CAM training/evaluation data and the trainer. It does not need the production repository or ChronoSpear benchmark answers.

## Local machine: prepare the upload bundle

From `research/chronospear_self_memory`:

```bash
python cam_native_dataset.py
rm -f cam_native_training_bundle.zip
zip -r cam_native_training_bundle.zip \
  cam_native_train.py \
  requirements-cam-native.txt \
  cam_native_data/train.jsonl \
  cam_native_data/eval.jsonl
```

Expected dataset counts:

```text
train_examples=704
eval_examples=176
skills=11
```

## Colab: select a GPU runtime

In Colab use **Runtime -> Change runtime type -> GPU**.

Before training, verify CUDA is visible:

```python
import torch
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO CUDA GPU")
```

Stop if the first line is `False`. Do not intentionally use `--allow-cpu` for this experiment.

## Colab: upload and unpack the bundle

Upload `cam_native_training_bundle.zip` using the Colab Files pane, then run:

```bash
!unzip -o cam_native_training_bundle.zip -d cam_native_training
%cd cam_native_training
```

Install the experiment dependencies:

```bash
!python -m pip install -q -r requirements-cam-native.txt
```

Restart the runtime only if Colab explicitly says a restart is required after dependency installation. If restarted, return to the unpacked training directory before continuing.

## Smoke training

Run the 20-optimizer-step smoke test first:

```bash
!python cam_native_train.py --smoke --output-dir cam_native_adapter_smoke
```

A valid run should print:

```text
CAM-NATIVE LORA TRAINING
model=Qwen/Qwen3-0.6B
train_examples=704
eval_examples=176
cuda=True
mode=SMOKE (20 optimizer steps)
```

If CUDA is `False`, stop rather than adding `--allow-cpu`.

## Full training

Once the smoke run succeeds:

```bash
!python cam_native_train.py --output-dir cam_native_adapter_qwen3_0_6b
```

The default experiment is:

- model: `Qwen/Qwen3-0.6B`
- LoRA rank: 16
- target modules: all linear layers
- epochs: 3
- learning rate: `1e-4`
- batch size: 1
- gradient accumulation: 8
- maximum sequence length: 1024
- assistant-only loss

Do not change these values for the first trained-vs-base comparison. The point is to establish a clean baseline.

## Colab: package the adapter

After training completes:

```bash
!zip -r cam_native_adapter_qwen3_0_6b.zip cam_native_adapter_qwen3_0_6b
```

Download `cam_native_adapter_qwen3_0_6b.zip` from the Colab Files pane.

## Local machine: install the adapter

Copy the downloaded zip into `research/chronospear_self_memory`, then:

```bash
rm -rf cam_native_adapter_qwen3_0_6b
unzip cam_native_adapter_qwen3_0_6b.zip
```

The expected local path is:

```text
research/chronospear_self_memory/cam_native_adapter_qwen3_0_6b/
```

## Local held-out evaluation

Run the exact same 176-example held-out policy evaluation used for the untrained baseline:

```bash
python cam_native_eval.py
```

Compare against the recorded base-only baseline:

```text
protocol_valid=4/176 (2.3%)
decision_signature_correct=0/176 (0.0%)
exact_output=0/176 (0.0%)
```

The important measurement is transfer to the held-out synthetic vocabulary and behavior families, not memorization of training strings.

## Real ChronoSpear handshake

Only after the adapter improves the held-out policy evaluation should it be connected to the real ChronoSpear CAM handshake. Keep the nine real benchmark questions out of training so this remains a genuine transfer test.
