"""Smart restart decider — pure logic.

Takes a list of changed file paths and a rule set, returns the actions
that should run (in stable execution order). Does not execute anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Rules:
    """Parsed rules document."""

    actions: dict[str, int]  # action_name -> sort order (lower runs first)
    rules: list[dict]  # raw rule list, each {pattern, actions}
    fallback: str | list[str]  # "all" | "none" | list of action names


@dataclass
class Decision:
    """Result of running the decider."""

    actions: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    fallback_applied: bool = False


_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob (with ``**`` support) to a compiled regex.

    ``**/`` matches zero or more path segments, ``**`` at end matches anything,
    ``*`` matches within a single segment, ``?`` matches one non-slash char.
    """
    cached = _REGEX_CACHE.get(pattern)
    if cached is not None:
        return cached

    i = 0
    out: list[str] = []
    n = len(pattern)
    while i < n:
        if pattern[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1

    regex = re.compile("^" + "".join(out) + "$")
    _REGEX_CACHE[pattern] = regex
    return regex


def glob_match(path: str, pattern: str) -> bool:
    """Match a path against a glob pattern supporting ``**`` recursion."""
    return bool(_glob_to_regex(pattern).match(path))


def load_rules(path: Path) -> Rules:
    """Load and validate a rules YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"rules file missing: {path}")

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"rules file must be a mapping at top level: {path}")

    raw_actions = data.get("actions") or {}
    if not isinstance(raw_actions, dict):
        raise ValueError("'actions' must be a mapping of name -> {order: int}")

    actions: dict[str, int] = {}
    for name, spec in raw_actions.items():
        if isinstance(spec, dict):
            order = int(spec.get("order", 100))
        elif spec is None:
            order = 100
        else:
            raise ValueError(f"action '{name}' spec must be a mapping or null")
        actions[name] = order

    raw_rules = data.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ValueError("'rules' must be a list")

    fallback = data.get("fallback", "none")
    if not isinstance(fallback, (str, list)):
        raise ValueError("'fallback' must be a string or list of action names")

    return Rules(actions=actions, rules=raw_rules, fallback=fallback)


def decide(changed_files: list[str], rules: Rules) -> Decision:
    """Decide which actions to run for the given changed files.

    First-match-wins: rules are evaluated top-to-bottom, only the first matching
    rule contributes its actions for a given file. Files that match no rule are
    collected into ``unmatched`` and the fallback policy decides their effect.
    """
    matched_actions: set[str] = set()
    unmatched: list[str] = []

    for raw_path in changed_files:
        path = raw_path.strip()
        if not path:
            continue

        for rule in rules.rules:
            pattern = rule.get("pattern", "")
            if pattern and glob_match(path, pattern):
                rule_actions = rule.get("actions") or []
                for action in rule_actions:
                    if action not in rules.actions:
                        raise ValueError(
                            f"rule pattern {pattern!r} references unknown action "
                            f"{action!r} (not declared in 'actions')"
                        )
                    matched_actions.add(action)
                break
        else:
            unmatched.append(path)

    fallback_applied = False
    if unmatched:
        if rules.fallback == "all":
            matched_actions.update(rules.actions.keys())
            fallback_applied = True
        elif isinstance(rules.fallback, list):
            for action in rules.fallback:
                if action not in rules.actions:
                    raise ValueError(
                        f"fallback references unknown action {action!r}"
                    )
                matched_actions.add(action)
            fallback_applied = True
        # "none" → unmatched files contribute no actions

    ordered = sorted(matched_actions, key=lambda a: (rules.actions[a], a))
    return Decision(
        actions=ordered,
        unmatched=unmatched,
        fallback_applied=fallback_applied,
    )
