"""Reverse import-chain expansion.

Given a project root and a list of changed Python files, walk the static import
graph in reverse to find every file that transitively imports any of them.
The expanded list is then fed back to the rule decider — so editing a leaf
utility correctly triggers restart of every service that touches it.

Limitations (documented; v0.1):
- Star imports are tracked at module granularity only.
- Dynamic imports (``importlib.import_module``) are not tracked.
- Conditional imports inside functions are treated as top-level imports
  (over-conservative — better to restart too much than too little).
- Only one source root per invocation. Multi-root monorepos can pre-merge
  the graphs by calling ``build_graph`` per root.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = frozenset(
    {"__pycache__", "venv", ".venv", "env", ".env", "build", "dist", ".git"}
)


@dataclass(frozen=True)
class ImportGraph:
    """Static import graph rooted at ``root``.

    ``importers[target]`` is the set of files that directly import ``target``
    (paths are relative POSIX strings, e.g. ``"src/api/handlers.py"``).
    """

    root: Path
    importers: dict[str, set[str]] = field(default_factory=dict)

    def reverse_closure(self, seeds: set[str]) -> set[str]:
        """Return ``seeds`` plus every file that transitively imports any seed."""
        seen: set[str] = set(seeds)
        queue: deque[str] = deque(seeds)
        while queue:
            current = queue.popleft()
            for upstream in self.importers.get(current, ()):
                if upstream not in seen:
                    seen.add(upstream)
                    queue.append(upstream)
        return seen


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.parts):
            continue
        files.append(path)
    return files


def _module_index(root: Path, files: list[Path]) -> dict[str, str]:
    """Map dotted module name -> relative POSIX path inside ``root``.

    A package (directory with ``__init__.py``) is indexed under its dotted name
    pointing to the ``__init__.py`` file. A submodule ``foo/bar.py`` is indexed
    under ``foo.bar`` pointing to ``foo/bar.py``.
    """
    index: dict[str, str] = {}
    for path in files:
        rel = path.relative_to(root)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]  # strip .py
        if not parts:
            continue
        dotted = ".".join(parts)
        index[dotted] = rel.as_posix()
    return index


def _resolve_relative(
    importer_rel: str, module: str, level: int
) -> str | None:
    """Resolve a relative ``from .x.y import z`` to a dotted module name."""
    parts = importer_rel.split("/")
    # Drop the file's own basename and walk up ``level - 1`` package directories.
    parts = parts[:-1]
    for _ in range(level - 1):
        if not parts:
            return None
        parts.pop()
    if module:
        parts.extend(module.split("."))
    if not parts:
        return None
    return ".".join(parts)


def _extract_import_targets(
    source: str, importer_rel: str, index: dict[str, str]
) -> set[str]:
    """Return the set of project files that ``importer_rel``'s source imports."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hit = index.get(alias.name)
                if hit:
                    targets.add(hit)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            if node.level > 0:
                resolved = _resolve_relative(importer_rel, module, node.level)
                if resolved is None:
                    continue
                base = resolved
            else:
                base = module

            if not base:
                continue

            # ``from base import name1, name2`` — try each name as a submodule
            # first (``base.nameN``), then fall back to ``base`` itself if any
            # alias was actually a module in the project.
            base_hit = index.get(base)
            for alias in node.names:
                child = f"{base}.{alias.name}"
                child_hit = index.get(child)
                if child_hit:
                    targets.add(child_hit)
                elif base_hit:
                    targets.add(base_hit)

            # ``from base import *`` resolves only to base itself.
            if not node.names and base_hit:
                targets.add(base_hit)

    return targets


def build_graph(root: Path) -> ImportGraph:
    """Build a reverse-import graph rooted at ``root``."""
    root = root.resolve()
    files = _iter_python_files(root)
    index = _module_index(root, files)

    importers: dict[str, set[str]] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for target in _extract_import_targets(source, rel, index):
            if target == rel:
                continue
            importers.setdefault(target, set()).add(rel)

    return ImportGraph(root=root, importers=importers)


def expand_changed(
    changed: list[str], graph: ImportGraph
) -> tuple[list[str], list[str]]:
    """Expand ``changed`` to include every transitive importer.

    Returns ``(expanded_files, added_files)``. ``expanded_files`` preserves the
    original order with newly-added files appended. Non-Python paths in
    ``changed`` are passed through untouched and never trigger expansion.
    """
    seeds: set[str] = set()
    passthrough: list[str] = []
    seen: set[str] = set()
    ordered: list[str] = []

    for raw in changed:
        path = raw.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
        if path.endswith(".py"):
            seeds.add(path)
        else:
            passthrough.append(path)

    closure = graph.reverse_closure(seeds)
    added: list[str] = []
    for path in sorted(closure - seeds):
        if path not in seen:
            seen.add(path)
            added.append(path)

    return ordered + added, added
