# smart-restart

> Rules-as-config restart decider for Python services. Don't restart your whole stack on every git push.

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#status)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)

## The problem

You ship a one-line bug fix to one service in your monorepo. Your deploy script restarts everything — bot, API, worker, scheduler — and you eat 30 seconds of cold starts and dropped connections, every time.

Most CI/CD scripts pick between two extremes:

- **Restart everything always.** Safe, but wasteful and slow.
- **Hand-maintained "if file in dir then restart X."** Fast, but rots silently when imports cross boundaries: someone refactors `utils/db.py` and forgets that `worker/jobs.py` imports it, the worker keeps the old code, you get a Heisenbug at 3 a.m.

`smart-restart` is the middle ground: a small decider that takes the list of changed files and a YAML rule set, then prints which actions are needed. Optionally, it walks the AST-derived import graph in reverse so editing a leaf utility correctly triggers restarts for every service that imports it.

It does **not** run the actions. Your deploy script does. `smart-restart` just decides.

## Quick start

```bash
pip install smart-restart  # coming with v0.1.0
```

Write a `restart-rules.yaml`:

```yaml
actions:
  pip_install:
    order: 10        # lower = runs earlier
  restart_api:
    order: 20

rules:
  - pattern: "requirements.txt"
    actions: [pip_install, restart_api]
  - pattern: "src/**"
    actions: [restart_api]
  - pattern: "**/*.md"
    actions: []      # explicitly do nothing

fallback: [restart_api]   # for files that match no rule
```

Pipe a diff into it:

```bash
$ git diff --name-only HEAD~1 HEAD | smart-restart
pip_install
restart_api
```

That's the output your deploy script consumes. Wire it into bash, Ansible, GitHub Actions, anything that takes stdout.

## Import-chain expansion (the interesting bit)

The base decider only knows about files you literally changed. That misses the case where a leaf module changes and dependents don't.

Pass `--root <project>` and `smart-restart` will parse every `.py` file under `<project>`, build a static import graph, and expand the changed file list to include every transitive importer:

```
src/
  utils/db.py        # you changed this
  api/handlers.py    # imports utils.db
  worker/jobs.py     # imports utils.db
```

```bash
$ echo "src/utils/db.py" | smart-restart --root src --show-expanded
INFO: import-chain expansion added 2 file(s):
  + smart_restart/api/handlers.py
  + smart_restart/worker/jobs.py
restart_api
restart_worker
```

If `restart-rules.yaml` only matches `src/api/**` to `restart_api` and `src/worker/**` to `restart_worker`, the expansion ensures both fire even though only `db.py` was in the diff.

### `--root` and src-layout

If your project uses src-layout (code under `src/your_pkg/`), pass `--root src`, **not** `--root .`. The graph indexes files by their dotted module name; the dotted name has to match what your imports actually say (`from your_pkg.foo` resolves to `<root>/your_pkg/foo.py`).

| Layout | Use |
|--------|-----|
| `src/your_pkg/...` (src-layout) | `--root src` |
| `your_pkg/...` (flat / package at root) | `--root .` |
| Multiple roots (e.g. `services/api/`, `services/worker/`) | run once per root, merge actions yourself |

## Why a separate decider

- **One source of truth.** Change `restart-rules.yaml`, every script that consumes the decider stays in sync.
- **Composable.** Pipe it into bash, Ansible, GitHub Actions, anything that takes stdout. No framework lock-in.
- **Diffable.** Restart rules live in version control, not buried in a shell script.
- **Testable.** Pure function, no side effects, hermetic.

## Configuration reference

```yaml
actions:                 # required: action name -> {order: int}
  <name>:
    order: <int>         # lower = runs earlier; default 100

rules:                   # required: list, evaluated top-down, first match wins
  - pattern: <glob>      # ** matches across directories, * within one segment
    actions: [<name>...] # actions to fire (use [] to explicitly skip)

fallback:                # what to do for files that match no rule
  none                   # default: contribute no actions
  | all                  # fire every declared action
  | [<name>...]          # fire just these
```

**First-match-wins** semantics: each file is matched against `rules` top-to-bottom, only the first hit contributes. This lets you put a narrow `**/*.md → []` rule above a broad `src/** → [restart_api]` rule.

## Status

🚧 **Alpha — extracted from a closed-source dogfood project (~2 years of daily use).**

Done in v0.1:
- [x] Generic rule engine with first-match-wins semantics
- [x] YAML-declared actions (no hardcoded service names)
- [x] Import-chain reverse closure (AST-based)
- [x] Glob patterns with `**` recursion
- [x] Pure decider — no execution, no side effects
- [x] 37 unit tests, fixture-driven

Deferred to v0.2+:
- LLM fallback for unmatched files (the upstream project has it; needs to be re-cast as a plugin to keep v0.1 dependency-free)
- Multi-root graph merge in one invocation
- Auto-detection of src-layout from `pyproject.toml`
- Star-import edge tracking at the symbol level

## License

[MIT](LICENSE)
