from pathlib import Path

import pytest

from smart_restart.decider import (
    Decision,
    Rules,
    decide,
    glob_match,
    load_rules,
)


# ---------- glob_match ----------

@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("src/api.py", "src/**", True),
        ("src/api.py", "src/*.py", True),
        ("src/sub/api.py", "src/*.py", False),
        ("src/sub/deep/x.py", "src/**", True),
        ("README.md", "**/*.md", True),
        ("docs/guide.md", "**/*.md", True),
        ("requirements.txt", "requirements.txt", True),
        ("requirements.txt", "*.txt", True),
        ("pkg/requirements.txt", "*.txt", False),
        ("a.py", "?.py", True),
        ("ab.py", "?.py", False),
    ],
)
def test_glob_match(path: str, pattern: str, expected: bool) -> None:
    assert glob_match(path, pattern) is expected


# ---------- load_rules ----------

def test_load_rules_reads_basic_example() -> None:
    rules = load_rules(Path(__file__).parents[1] / "examples" / "basic.yaml")
    assert "pip_install" in rules.actions
    assert "restart_api" in rules.actions
    assert rules.actions["pip_install"] < rules.actions["restart_api"]
    assert rules.fallback == ["restart_api"]


def test_load_rules_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rules(tmp_path / "does-not-exist.yaml")


def test_load_rules_malformed_actions(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("actions: [not, a, mapping]\nrules: []\n")
    with pytest.raises(ValueError):
        load_rules(bad)


# ---------- decide ----------

def _rules(
    actions: dict[str, int] | None = None,
    rules: list[dict] | None = None,
    fallback: str | list[str] = "none",
) -> Rules:
    return Rules(
        actions=actions or {"pip_install": 10, "restart_api": 20},
        rules=rules or [],
        fallback=fallback,
    )


def test_decide_no_changes() -> None:
    result = decide([], _rules())
    assert result == Decision(actions=[], unmatched=[], fallback_applied=False)


def test_decide_first_match_wins() -> None:
    rules = _rules(
        rules=[
            {"pattern": "requirements.txt", "actions": ["pip_install", "restart_api"]},
            {"pattern": "*.txt", "actions": ["restart_api"]},
        ],
    )
    result = decide(["requirements.txt"], rules)
    assert result.actions == ["pip_install", "restart_api"]
    assert result.unmatched == []


def test_decide_dedupes_actions_across_files() -> None:
    rules = _rules(
        rules=[
            {"pattern": "src/**", "actions": ["restart_api"]},
        ],
    )
    result = decide(["src/a.py", "src/b.py", "src/c.py"], rules)
    assert result.actions == ["restart_api"]


def test_decide_explicit_empty_actions_skips_action() -> None:
    rules = _rules(
        rules=[
            {"pattern": "**/*.md", "actions": []},
            {"pattern": "src/**", "actions": ["restart_api"]},
        ],
    )
    result = decide(["README.md", "src/api.py"], rules)
    assert result.actions == ["restart_api"]
    assert result.unmatched == []


def test_decide_unmatched_with_fallback_none() -> None:
    rules = _rules(
        rules=[{"pattern": "src/**", "actions": ["restart_api"]}],
        fallback="none",
    )
    result = decide(["unknown.bin"], rules)
    assert result.actions == []
    assert result.unmatched == ["unknown.bin"]
    assert result.fallback_applied is False


def test_decide_unmatched_with_fallback_all() -> None:
    rules = _rules(
        rules=[{"pattern": "src/**", "actions": ["restart_api"]}],
        fallback="all",
    )
    result = decide(["unknown.bin"], rules)
    assert result.actions == ["pip_install", "restart_api"]
    assert result.fallback_applied is True


def test_decide_unmatched_with_fallback_list() -> None:
    rules = _rules(
        rules=[{"pattern": "src/**", "actions": ["restart_api"]}],
        fallback=["restart_api"],
    )
    result = decide(["unknown.bin"], rules)
    assert result.actions == ["restart_api"]
    assert result.fallback_applied is True


def test_decide_orders_by_action_order() -> None:
    rules = _rules(
        actions={"a": 30, "b": 10, "c": 20},
        rules=[{"pattern": "x", "actions": ["a", "b", "c"]}],
    )
    result = decide(["x"], rules)
    assert result.actions == ["b", "c", "a"]


def test_decide_unknown_action_raises() -> None:
    rules = _rules(rules=[{"pattern": "x", "actions": ["nonexistent"]}])
    with pytest.raises(ValueError, match="unknown action"):
        decide(["x"], rules)


def test_decide_unknown_fallback_action_raises() -> None:
    rules = _rules(
        rules=[{"pattern": "src/**", "actions": ["restart_api"]}],
        fallback=["nonexistent"],
    )
    with pytest.raises(ValueError, match="fallback references unknown action"):
        decide(["other.bin"], rules)
