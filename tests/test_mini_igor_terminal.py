from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_RESEARCH = Path(__file__).parents[1] / "research" / "chronospear_self_memory"
sys.path.insert(0, str(_RESEARCH))
terminal_module: Any = importlib.import_module("mini_igor")
tool_module: Any = importlib.import_module("world_question_tools")
fixtures: Any = importlib.import_module("test_world_question")


class Inputs:
    def __init__(self, *values: str) -> None:
        self.values = iter(values)

    def __call__(self, _prompt: str) -> str:
        return next(self.values)


def answered(question: str, answer: str) -> Any:
    return tool_module.ToolQuestionResult(
        question=question,
        world="test-world",
        status="answered",
        answer=answer,
        llm_calls=2,
        cam_tool_calls=2,
        history_calls=1,
        initial_activations=1,
        cam_estimated_tokens=40,
        provider_prompt_tokens=12,
        provider_completion_tokens=4,
        provider_retries=1,
        cam_time_ms=1.5,
        provider_time_ms=2.5,
        wall_time_ms=4.5,
        navigation_trace=["LANGUAGE-ACTIVATE: David Steele", "submit_answer(...)"],
    )


def terminal(tmp_path: Path, runner: Any) -> Any:
    return terminal_module.MiniIgorTerminal(
        fixtures._package(tmp_path),
        provider=object(),
        provider_name="mock",
        model="mock-model",
        runner=runner,
    )


def test_query_loop_prints_answer_and_passes_bounded_recent_context(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    def runner(_world: Path, question: str, **kwargs: Any) -> Any:
        calls.append((question, kwargs["recent_context"]))
        return answered(question, f"Answer {len(calls)}")

    repl = terminal(tmp_path, runner)
    output: list[str] = []
    questions = (
        "Who is David Steele?",
        "What happened to him?",
        "Question three?",
        "Question four?",
        "Question five?",
        "Question six?",
    )
    repl.run(Inputs(*questions, "/quit"), output.append)

    assert calls[0][1] == ()
    assert calls[1][1] == (
        tool_module.RecentConversationTurn("Who is David Steele?", "Answer 1"),
    )
    assert len(calls[-1][1]) == terminal_module.RECENT_TURN_LIMIT
    assert calls[-1][1][0].user == "What happened to him?"
    assert "Smeagol > Answer 1" in output
    assert "Smeagol > Answer 2" in output
    assert len(repl.recent_turns) <= terminal_module.RECENT_TURN_LIMIT


def test_each_query_uses_a_fresh_runner_result_and_no_cam_state_is_forwarded(
    tmp_path: Path,
) -> None:
    results = iter(
        (
            answered("First?", "First answer"),
            answered("Second?", "Second answer"),
        )
    )
    kwargs_seen: list[dict[str, object]] = []

    def runner(_world: Path, _question: str, **kwargs: object) -> Any:
        kwargs_seen.append(kwargs)
        return next(results)

    repl = terminal(tmp_path, runner)
    repl.run(Inputs("First?", "Second?", "/quit"), lambda _line: None)

    assert len(kwargs_seen) == 2
    assert set(kwargs_seen[1]) == {"provider_fn", "max_rounds", "recent_context"}
    assert "session" not in kwargs_seen[1]
    assert "admitted_evidence" not in kwargs_seen[1]


def test_trace_toggle_changes_display_only(tmp_path: Path) -> None:
    calls = 0

    def runner(_world: Path, question: str, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        return answered(question, "Grounded answer")

    repl = terminal(tmp_path, runner)
    output: list[str] = []
    repl.run(
        Inputs("/trace on", "First?", "/trace off", "Second?", "/quit"),
        output.append,
    )

    assert calls == 2
    assert output.count("[trace]") == 1
    assert output.count("submit_answer(...)") == 1


def test_stats_clear_world_and_quit_are_local_and_non_mutating(tmp_path: Path) -> None:
    package = fixtures._package(tmp_path)
    original = (package / "memory.json").read_bytes()

    def runner(_world: Path, question: str, **_kwargs: object) -> Any:
        return answered(question, "Grounded answer")

    repl = terminal(tmp_path, runner)
    output: list[str] = []
    repl.run(
        Inputs("/stats", "Question?", "/stats", "/world", "/clear", "/stats", "/exit"),
        output.append,
    )

    assert output.count("No query has run yet.") == 2
    assert "status: answered" in output
    assert "LLM calls: 2" in output
    assert "Identities: 6" in output
    assert "Associations: 4" in output
    assert "Historical Occurrences: 7" in output
    assert repl.recent_turns == []
    assert repl.last_result is None
    assert (package / "memory.json").read_bytes() == original


def test_recoverable_query_failure_returns_to_prompt(tmp_path: Path) -> None:
    calls = 0

    def runner(_world: Path, question: str, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return tool_module.ToolQuestionResult(
                question=question,
                world="test-world",
                status="provider_failure",
                error="sanitized provider error",
            )
        return answered(question, "Recovered answer")

    repl = terminal(tmp_path, runner)
    output: list[str] = []
    repl.run(Inputs("First?", "Second?", "/quit"), output.append)

    assert calls == 2
    assert any("provider_failure" in line for line in output)
    assert "Smeagol > Recovered answer" in output


@pytest.mark.parametrize("terminator", [EOFError(), KeyboardInterrupt()])
def test_terminal_handles_eof_and_interrupt(tmp_path: Path, terminator: BaseException) -> None:
    def stop(_prompt: str) -> str:
        raise terminator

    repl = terminal(tmp_path, lambda *_args, **_kwargs: answered("", ""))
    output: list[str] = []
    repl.run(stop, output.append)

    assert output[-1] == "Smeagol session ended."
