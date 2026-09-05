"""Small interactive terminal for Smeagol, the tool-driven CAM Librarian."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from llama_cpp_provider import LlamaCppToolProvider
from world_question_tools import (
    GroqCamToolProvider,
    RecentConversationTurn,
    ToolProvider,
    ToolQuestionResult,
    run_world_question_tools,
)

from chronospear.world_import import import_world

RECENT_TURN_LIMIT = 4

HELP = """Commands:
  /help       Show this help.
  /trace on   Show observable navigation after each query.
  /trace off  Hide navigation traces.
  /stats      Show telemetry for the most recent query.
  /clear      Clear recent conversation and last-query display state.
  /world      Show the current world path and object counts.
  /quit       Exit Smeagol. (/exit also works.)"""

Runner = Callable[..., ToolQuestionResult]
Output = Callable[[str], None]
Input = Callable[[str], str]


class MiniIgorTerminal:
    """Ephemeral conversational shell over fresh Tool Librarian sessions."""

    def __init__(
        self,
        world_path: str | Path,
        *,
        provider: ToolProvider,
        provider_name: str,
        model: str,
        runner: Runner = run_world_question_tools,
        max_rounds: int = 10,
    ) -> None:
        self.world_path = Path(world_path)
        self.provider = provider
        self.provider_name = provider_name
        self.model = model
        self.runner = runner
        self.max_rounds = max_rounds
        self.recent_turns: list[RecentConversationTurn] = []
        self.last_result: ToolQuestionResult | None = None
        self.trace_enabled = False

    def startup(self, output: Output = print) -> None:
        output("=" * 60)
        output("SMEAGOL")
        output("=" * 60)
        output(f"World: {self.world_path}")
        output(f"Provider: {self.provider_name}")
        output(f"Model: {self.model}")
        output("")
        output("Type /help for commands.")

    def run(self, input_fn: Input = input, output: Output = print) -> None:
        self.startup(output)
        while True:
            try:
                text = input_fn("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                output("")
                output("Smeagol session ended.")
                return
            if not text:
                continue
            if text.startswith("/"):
                if self._command(text, output):
                    return
                continue
            self._query(text, output)

    def _query(self, question: str, output: Output) -> None:
        result = self.runner(
            self.world_path,
            question,
            provider_fn=self.provider,
            max_rounds=self.max_rounds,
            recent_context=tuple(self.recent_turns),
        )
        self.last_result = result
        if result.status == "answered" and result.answer is not None:
            answer = result.answer
            output(f"Smeagol > {answer}")
            self.recent_turns.append(RecentConversationTurn(question, answer))
            self.recent_turns = self.recent_turns[-RECENT_TURN_LIMIT:]
        else:
            detail = result.error or result.status
            output(f"Smeagol > Query failed ({result.status}): {detail}")
        if self.trace_enabled:
            self._print_trace(result, output)

    def _command(self, text: str, output: Output) -> bool:
        normalized = " ".join(text.casefold().split())
        if normalized in {"/quit", "/exit"}:
            output("Smeagol session ended.")
            return True
        if normalized == "/help":
            output(HELP)
        elif normalized == "/trace on":
            self.trace_enabled = True
            output("Trace enabled.")
        elif normalized == "/trace off":
            self.trace_enabled = False
            output("Trace disabled.")
        elif normalized == "/stats":
            self._print_stats(output)
        elif normalized == "/clear":
            self.recent_turns.clear()
            self.last_result = None
            output("Recent conversation and last-query state cleared.")
        elif normalized == "/world":
            self._print_world(output)
        else:
            output(f"Unknown command: {text}. Type /help for commands.")
        return False

    def _print_trace(self, result: ToolQuestionResult, output: Output) -> None:
        output("[trace]")
        if result.navigation_trace:
            for operation in result.navigation_trace:
                output(operation)
        else:
            output("- no navigation events")
        if result.suggestions:
            output("[suggestions]")
            for suggestion in result.suggestions:
                output(f"{suggestion.kind} | {suggestion.name}")
                output(f"Reason: {suggestion.reason}")

    def _print_stats(self, output: Output) -> None:
        result = self.last_result
        if result is None:
            output("No query has run yet.")
            return
        output("[stats]")
        fields: tuple[tuple[str, Any], ...] = (
            ("status", result.status),
            ("LLM calls", result.llm_calls),
            ("CAM tool calls", result.cam_tool_calls),
            ("searches", result.searches),
            ("history calls", result.history_calls),
            ("association calls", result.association_calls),
            ("description calls", result.description_calls),
            ("initial activations", result.initial_activations),
            ("explicit activations", result.explicit_activations),
            ("CAM admitted estimated tokens", result.cam_estimated_tokens),
            ("provider prompt tokens", result.provider_prompt_tokens),
            ("provider completion tokens", result.provider_completion_tokens),
            ("provider retries", result.provider_retries),
            ("CAM time", f"{result.cam_time_ms:.3f} ms"),
            ("provider time", f"{result.provider_time_ms:.3f} ms"),
            ("wall time", f"{result.wall_time_ms:.3f} ms"),
        )
        for label, value in fields:
            output(f"{label}: {value}")

    def _print_world(self, output: Output) -> None:
        try:
            world = import_world(self.world_path)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            output(f"World unavailable: {exc}")
            return
        output(f"World: {self.world_path}")
        output(f"Identities: {len(world.identities.all())}")
        output(f"Associations: {len(world.associations.all())}")
        output(f"Historical Occurrences: {len(world.occurrences.all())}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Talk to Smeagol over production CAM.")
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--provider", choices=("groq", "llama-cpp"), default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--tool-choice", choices=("auto", "required"), default="auto")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--llama-timeout", type=float, default=120.0)
    parser.add_argument("--max-rounds", type=int, default=10)
    args = parser.parse_args()

    provider: ToolProvider
    if args.provider == "llama-cpp":
        provider = LlamaCppToolProvider(
            base_url=args.llama_url,
            model=args.model,
            tool_choice=args.tool_choice,
            timeout_seconds=args.llama_timeout,
        )
    else:
        provider = GroqCamToolProvider(args.model, args.tool_choice)
    MiniIgorTerminal(
        args.world,
        provider=provider,
        provider_name=args.provider,
        model=args.model,
        max_rounds=args.max_rounds,
    ).run()


if __name__ == "__main__":
    main()
