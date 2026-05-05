# Changelog

English | [繁體中文](CHANGELOG.zh-TW.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-06

Initial public release. A drop-in restart decider for Python services: takes a list of changed files and a YAML rule set, prints which actions are needed. Optionally walks the AST-derived import graph in reverse so editing a leaf utility correctly triggers restarts for every service that imports it.

### Added

#### Core decider

- Pure-function rule engine: `decide(changed_files, rules) -> Decision`
- First-match-wins glob matching with `**` recursion (custom regex translation, cached per pattern)
- YAML-declared actions with explicit ordering (`order: int`, lower runs first)
- Three fallback policies for unmatched files:
  - `none` — unmatched files contribute nothing (default)
  - `all` — fire every declared action
  - `[action_list]` — fire just the specified actions
- Actions referenced in rules or fallback that aren't declared raise `ValueError` early (no silent typos)

#### Import-chain expansion (`--root <path>`)

- AST-based static analysis of the project source tree
- Reverse closure: changing a file pulls in every transitive importer for restart consideration
- Resolves three import forms uniformly:
  - `import pkg.foo`
  - `from pkg import foo` (foo as submodule)
  - `from pkg.foo import X` (X as name)
- Handles relative imports (`from .leaf import X`)
- Skips `__pycache__`, `.venv`, dotted directories
- Survives files with syntax errors (no crash, just no edges)
- Path prefix support so `git diff` output (project-relative) lines up with `--root src` (root-relative)

#### CLI

- `smart-restart -r <rules.yaml>` — read changed files from stdin, print actions
- `--root <path>` — enable import-chain expansion
- `--show-unmatched` — print unmatched file list to stderr
- `--show-expanded` — print files added by import-chain expansion to stderr
- Stable, scriptable output: actions on stdout, diagnostics on stderr

#### Documentation

- Bilingual README (English + Traditional Chinese) — quick start, configuration reference, src-layout gotcha table
- `docs/architecture.md` — design pillars, module-resolution algorithm, conservative-by-default philosophy, what didn't survive extraction from upstream, v0.2 open questions
- Three worked examples in `examples/`:
  - `basic` — single web service
  - `multi-service` — three services sharing a code tree, the canonical "why `--root` exists" walkthrough
  - `monorepo` — independent source trees, run once per tree and union outputs

#### Project infrastructure

- 39 tests across `decider` and `import_graph`, all hermetic via `tmp_path`
- GitHub Actions CI: ruff lint + pytest on Python 3.11 / 3.12 / 3.13
- PyPI Trusted Publisher (OIDC) configured
- Community files: `CONTRIBUTING.md`, issue + PR templates (deferred to v0.2 if missing here)

### Notes

- **No execution.** `smart-restart` prints actions and exits; downstream scripts run them. This is by design (see `docs/architecture.md`).
- **LLM fallback deferred to v0.2.** The upstream project uses Claude to classify unmatched files; v0.1 keeps the library dependency-free. v0.2 will re-cast it as an opt-in plugin.
- **Multi-root graph merge deferred to v0.2.** Today, monorepos invoke the decider once per source root. The example shows a small bash wrapper that does the union.
- **src-layout auto-detection deferred to v0.2.** Users currently pass `--root src` manually for src-layout projects.

[Unreleased]: https://github.com/zx22413/smart-restart/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zx22413/smart-restart/releases/tag/v0.1.0
