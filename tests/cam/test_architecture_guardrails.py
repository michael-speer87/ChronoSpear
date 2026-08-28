import ast
from pathlib import Path


def test_slice_one_domain_models_do_not_reintroduce_ambiguous_tick_fields() -> None:
    """WT/ST meaning must remain explicit instead of collapsing into raw tick ints."""

    source_root = Path(__file__).parents[2] / "src" / "chronospear"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in {"tick", "at_tick", "known_at"}:
                    offenders.append(f"{path.name}:{node.lineno}:{node.target.id}")

    assert offenders == []
