from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA/SFT a small Qwen3 model on CAM-native navigation behavior.")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--train", default="cam_native_data/train.jsonl")
    parser.add_argument("--eval", default="cam_native_data/eval.jsonl")
    parser.add_argument("--output-dir", default="cam_native_adapter_qwen3_0_6b")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--smoke", action="store_true", help="Run only 20 optimizer steps to verify the stack.")
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Explicitly allow very slow CPU training. Without this flag, training refuses to start if CUDA is unavailable.",
    )
    args = parser.parse_args()

    try:
        import torch
        from datasets import load_dataset
        from packaging.version import Version
        from peft import LoraConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install the CAM-native training requirements first. "
            f"Original import error: {exc}"
        ) from exc

    # Google Colab may preinstall an old optional torchao package. Current PEFT
    # raises during LoRA injection when torchao is present but < 0.16.0, even
    # though this experiment does not use torchao quantization. Fail before the
    # model download with a precise remediation instead of crashing later.
    try:
        torchao_version = version("torchao")
    except PackageNotFoundError:
        torchao_version = None
    if torchao_version is not None and Version(torchao_version) < Version("0.16.0"):
        raise SystemExit(
            f"Incompatible optional torchao detected: {torchao_version}. "
            "This experiment does not use torchao. Remove the stale package with "
            "`python -m pip uninstall -y torchao`, then rerun training."
        )

    train_path = Path(args.train)
    eval_path = Path(args.eval)
    if not train_path.exists() or not eval_path.exists():
        raise SystemExit("Training/eval JSONL missing. Run cam_native_dataset.py first.")

    cuda = torch.cuda.is_available()
    if not cuda and not args.allow_cpu:
        raise SystemExit(
            "CUDA GPU not detected. Refusing to start LoRA training on CPU by default. "
            "Use a CUDA environment for the real experiment, or pass --allow-cpu only if you intentionally want CPU training."
        )

    dataset = load_dataset(
        "json",
        data_files={"train": str(train_path), "eval": str(eval_path)},
    )

    bf16 = bool(cuda and torch.cuda.is_bf16_supported())
    fp16 = bool(cuda and not bf16)

    if not cuda:
        print("WARNING: CPU training explicitly enabled. Expect this to be much slower than CUDA training.")

    peft_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_rank * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )

    training_args = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        max_steps=20 if args.smoke else -1,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        # Current TRL/Transformers interprets a float < 1 as a ratio of total steps.
        warmup_steps=0.05,
        logging_steps=5,
        save_strategy="epoch" if not args.smoke else "no",
        eval_strategy="no",
        report_to="none",
        seed=417,
        data_seed=417,
        bf16=bf16,
        fp16=fp16,
        use_cpu=not cuda,
        gradient_checkpointing=True,
        max_length=args.max_length,
        assistant_only_loss=True,
        packing=False,
    )

    print("CAM-NATIVE LORA TRAINING")
    print(f"model={args.model}")
    print(f"train_examples={len(dataset['train'])}")
    print(f"eval_examples={len(dataset['eval'])}")
    print(f"cuda={cuda} bf16={bf16} fp16={fp16}")
    print(f"torch={version('torch')} transformers={version('transformers')} trl={version('trl')} peft={version('peft')}")
    print(f"lora_rank={args.lora_rank} target_modules=all-linear")
    print(f"output_dir={Path(args.output_dir).resolve()}")
    if args.smoke:
        print("mode=SMOKE (20 optimizer steps)")

    trainer = SFTTrainer(
        model=args.model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        peft_config=peft_config,
    )
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(args.output_dir)

    print("TRAINING COMPLETE")
    for key, value in sorted(metrics.items()):
        print(f"{key}={value}")
    print(f"adapter_dir={Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
