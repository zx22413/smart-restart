"""smart-restart command-line entry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .decider import decide, load_rules
from .import_graph import build_graph, expand_changed


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
        "--root",
        type=Path,
        default=None,
        help=(
            "project source root. When set, the decider expands changed Python "
            "files via reverse import-chain closure before matching rules — so "
            "editing a leaf utility correctly triggers restart of every service "
            "that imports it."
        ),
    )
    parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="print unmatched file list to stderr",
    )
    parser.add_argument(
        "--show-expanded",
        action="store_true",
        help="when --root is set, print files added by import-chain expansion",
    )
    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    changed = [line for line in sys.stdin.read().splitlines() if line.strip()]

    if args.root is not None:
        # Derive the project-relative prefix so graph paths match what the
        # caller's ``git diff`` emits. Absolute roots outside cwd skip the
        # prefix and require root-relative input.
        root_arg = args.root
        if root_arg.is_absolute():
            try:
                rel = root_arg.relative_to(Path.cwd())
            except ValueError:
                rel = None
        else:
            rel = root_arg
        prefix = ""
        if rel is not None:
            posix = rel.as_posix().strip("/")
            if posix and posix != ".":
                prefix = posix

        graph = build_graph(args.root, path_prefix=prefix)
        changed, added = expand_changed(changed, graph)
        if args.show_expanded and added:
            print(
                f"INFO: import-chain expansion added {len(added)} file(s):",
                file=sys.stderr,
            )
            for path in added:
                print(f"  + {path}", file=sys.stderr)

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
