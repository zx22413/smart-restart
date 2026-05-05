"""smart-restart command-line entry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .decider import decide, load_rules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smart-restart",
        description=(
            "Decide which restart actions are needed for a list of changed files. "
            "Reads file paths from stdin (one per line)."
        ),
    )
    parser.add_argument(
        "-r",
        "--rules",
        type=Path,
        default=Path("restart-rules.yaml"),
        help="path to rules YAML (default: ./restart-rules.yaml)",
    )
    parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="print unmatched file list to stderr",
    )
    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    changed = [line for line in sys.stdin.read().splitlines() if line.strip()]

    try:
        decision = decide(changed, rules)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.show_unmatched and decision.unmatched:
        print(
            f"INFO: {len(decision.unmatched)} unmatched file(s):",
            file=sys.stderr,
        )
        for path in decision.unmatched:
            print(f"  - {path}", file=sys.stderr)
        if decision.fallback_applied:
            print("INFO: fallback policy applied", file=sys.stderr)

    for action in decision.actions:
        print(action)

    return 0


if __name__ == "__main__":
    sys.exit(main())
