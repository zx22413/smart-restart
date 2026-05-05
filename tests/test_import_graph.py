from pathlib import Path

from smart_restart.import_graph import build_graph, expand_changed


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_linear_chain_expands_upstream(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "from pkg import c\n")
    _write(tmp_path, "pkg/c.py", "VALUE = 1\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(["pkg/c.py"], graph)

    assert set(expanded) == {"pkg/a.py", "pkg/b.py", "pkg/c.py"}
    assert set(added) == {"pkg/a.py", "pkg/b.py"}


def test_relative_imports_resolve(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/sub/__init__.py", "")
    _write(tmp_path, "pkg/sub/leaf.py", "X = 1\n")
    _write(tmp_path, "pkg/sub/uses.py", "from .leaf import X\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(["pkg/sub/leaf.py"], graph)

    assert "pkg/sub/uses.py" in expanded
    assert added == ["pkg/sub/uses.py"]


def test_stdlib_and_third_party_imports_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import os\nimport sys\nimport requests\n")

    graph = build_graph(tmp_path)
    # No edges: all imports are external.
    assert graph.importers == {}
    expanded, added = expand_changed(["app.py"], graph)
    assert added == []
    assert expanded == ["app.py"]


def test_circular_import_terminates(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "from pkg import a\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(["pkg/a.py"], graph)
    assert set(expanded) == {"pkg/a.py", "pkg/b.py"}
    assert added == ["pkg/b.py"]


def test_non_python_files_pass_through(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/leaf.py", "X = 1\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(
        ["requirements.txt", "pkg/leaf.py", "README.md"], graph
    )

    assert "requirements.txt" in expanded
    assert "README.md" in expanded
    assert added == []  # only pkg/leaf.py is a Python seed, no importers


def test_skips_pycache_and_dotdirs(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/real.py", "X = 1\n")
    _write(tmp_path, "pkg/__pycache__/real.cpython-311.pyc", "junk\n")
    _write(tmp_path, ".venv/lib/foo.py", "import os\n")

    graph = build_graph(tmp_path)
    # __pycache__/.pyc files aren't .py so .rglob wouldn't catch them, but the
    # .venv tree must be skipped explicitly.
    files_seen = set(graph.importers.keys()) | {
        f for files in graph.importers.values() for f in files
    }
    assert all(".venv" not in f for f in files_seen)


def test_dotted_absolute_import(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/sub/__init__.py", "")
    _write(tmp_path, "pkg/sub/leaf.py", "X = 1\n")
    _write(tmp_path, "consumer.py", "import pkg.sub.leaf\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(["pkg/sub/leaf.py"], graph)

    assert "consumer.py" in expanded
    assert added == ["consumer.py"]


def test_from_package_import_submodule(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/leaf.py", "X = 1\n")
    _write(tmp_path, "consumer.py", "from pkg import leaf\n")

    graph = build_graph(tmp_path)
    expanded, _ = expand_changed(["pkg/leaf.py"], graph)
    assert "consumer.py" in expanded


def test_from_module_import_name(tmp_path: Path) -> None:
    """``from pkg.leaf import X`` (X is a name, not a module) → edge to pkg/leaf.py."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/leaf.py", "X = 1\n")
    _write(tmp_path, "consumer.py", "from pkg.leaf import X\n")

    graph = build_graph(tmp_path)
    expanded, _ = expand_changed(["pkg/leaf.py"], graph)
    assert "consumer.py" in expanded


def test_diamond_dependency(tmp_path: Path) -> None:
    """B and C both import D; A imports B and C. Changing D should pull in B, C, A."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/d.py", "X = 1\n")
    _write(tmp_path, "pkg/b.py", "from pkg import d\n")
    _write(tmp_path, "pkg/c.py", "from pkg import d\n")
    _write(tmp_path, "pkg/a.py", "from pkg import b, c\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed(["pkg/d.py"], graph)
    assert set(expanded) == {"pkg/a.py", "pkg/b.py", "pkg/c.py", "pkg/d.py"}
    assert set(added) == {"pkg/a.py", "pkg/b.py", "pkg/c.py"}


def test_syntax_error_in_file_does_not_crash(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/broken.py", "this is :: not python\n")
    _write(tmp_path, "pkg/ok.py", "X = 1\n")

    # Build should succeed; broken.py contributes no edges but doesn't crash.
    graph = build_graph(tmp_path)
    expanded, _ = expand_changed(["pkg/ok.py"], graph)
    assert "pkg/ok.py" in expanded


def test_empty_changed_list(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/leaf.py", "X = 1\n")

    graph = build_graph(tmp_path)
    expanded, added = expand_changed([], graph)
    assert expanded == []
    assert added == []


def test_path_prefix_makes_paths_project_relative(tmp_path: Path) -> None:
    """``--root src`` with ``path_prefix='src'`` lets users feed in
    ``git diff`` output (project-relative) and get matching graph keys."""
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/leaf.py", "X = 1\n")
    _write(tmp_path, "src/pkg/uses.py", "from pkg.leaf import X\n")

    graph = build_graph(tmp_path / "src", path_prefix="src")
    # Importer paths are now prefixed.
    assert any(p.startswith("src/") for p in graph.importers["src/pkg/leaf.py"])
    expanded, added = expand_changed(["src/pkg/leaf.py"], graph)
    assert "src/pkg/uses.py" in expanded
    assert added == ["src/pkg/uses.py"]


def test_path_prefix_preserves_relative_import_resolution(tmp_path: Path) -> None:
    """Relative imports inside the graph still resolve correctly when a
    prefix is applied (the prefix is purely for display, not resolution)."""
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/sub/__init__.py", "")
    _write(tmp_path, "src/pkg/sub/leaf.py", "X = 1\n")
    _write(tmp_path, "src/pkg/sub/uses.py", "from .leaf import X\n")

    graph = build_graph(tmp_path / "src", path_prefix="src")
    expanded, _ = expand_changed(["src/pkg/sub/leaf.py"], graph)
    assert "src/pkg/sub/uses.py" in expanded
