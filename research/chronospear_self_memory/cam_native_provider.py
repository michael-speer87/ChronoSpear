from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from live_quest import ProviderResult


@dataclass
class LocalCamNativeProvider:
    model_name: str = "Qwen/Qwen3-0.6B"
    adapter_path: str | None = "cam_native_adapter_qwen3_0_6b"
    max_new_tokens: int = 192

    def __post_init__(self) -> None:
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Missing local inference dependencies. Install the CAM-native training requirements first."
            ) from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        base = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype="auto",
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        if self.adapter_path:
            adapter = Path(self.adapter_path)
            if not adapter.exists():
                raise RuntimeError(f"CAM-native adapter not found: {adapter}")
            self._model = PeftModel.from_pretrained(base, str(adapter))
        else:
            self._model = base
        self._model.eval()

    def _format_chat(self, messages: list[dict[str, str]]) -> str:
        try:
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            # Fallback for a tokenizer/chat-template version without the hard switch.
            patched = [dict(message) for message in messages]
            if patched:
                patched[-1]["content"] = patched[-1]["content"] + "\n/no_think"
            return self._tokenizer.apply_chat_template(
                patched,
                tokenize=False,
                add_generation_prompt=True,
            )

    def __call__(self, messages: list[dict[str, str]]) -> ProviderResult:
        text = self._format_chat(messages)
        model_inputs = self._tokenizer([text], return_tensors="pt").to(self._model.device)
        input_tokens = int(model_inputs.input_ids.shape[-1])

        start = perf_counter()
        with self._torch.no_grad():
            generated = self._model.generate(
                **model_inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        elapsed = perf_counter() - start

        output_ids = generated[0][input_tokens:]
        completion_tokens = int(output_ids.shape[-1])
        output = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        if "</think>" in output:
            output = output.split("</think>", 1)[1].strip()

        return ProviderResult(
            output,
            {
                "prompt_tokens": input_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": input_tokens + completion_tokens,
                "total_time": elapsed,
            },
        )
