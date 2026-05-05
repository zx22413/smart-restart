# Architecture

How `smart-restart` is built, why each piece looks the way it does, and what didn't survive the extraction from the upstream project.

## Design pillars

### 1. Decider, not executor

`smart-restart` prints what should happen and exits. It never runs `systemctl`, never installs packages, never touches your services. The downstream consumer (your deploy script) is responsible for execution.

This is the single most important decision. A few reasons:

- **Composability.** `git diff | smart-restart | xargs -L1 ./restart.sh` works. So does feeding the output into Ansible playbooks, GitHub Actions matrix jobs, or a remote execution daemon. None of those care that the upstream is Python.
- **Testability.** The whole pipeline is `(changed_files, rules) -> actions: list[str]`. No subprocess calls, no filesystem mutation, no network. Every test runs in milliseconds with `tmp_path` fixtures.
- **Failure modes are obvious.** If the wrong service restarts, the bug is in the YAML or the import graph, not in some hidden orchestration layer. There is no orchestration layer.

The upstream project has an executor (a 255-line bash script that wraps the decider). That script intentionally lives outside this library. It's referenced as inspiration in `examples/` once those land.

### 2. Rules-as-config

Actions and patterns are YAML, not code. A user adds a new service by editing one file:

```yaml
actions:
  restart_new_thing:
    order: 30

rules:
  - pattern: "src/new_thing/**"
    actions: [restart_new_thing]
```

No subclassing, no plugin registration, no "extend the AbstractAction interface." The YAML *is* the interface.

### 3. First-match-wins

Rules are evaluated top-to-bottom. Only the first matching rule contributes its actions for a given changed file. This is intentional and makes precedence locally readable:

```yaml
rules:
  - pattern: "**/*.md"
    actions: []                    # docs are explicitly inert
  - pattern: "src/**"
    actions: [restart_api]         # everything else under src restarts api
```

If you read top-to-bottom you get the precedence right. The alternative (collect-all-matches) sounds more general but quickly produces YAML where understanding "what does this file do" requires scanning the entire rule set.

The upstream version uses the same semantics — confirmed to work over two years of daily use across hundreds of commits.

## The decider (`decider.py`)

A pure function:

```python
def decide(changed_files: list[str], rules: Rules) -> Decision: ...
```

`Rules` is a frozen dataclass parsed from YAML. `Decision` carries:

- `actions: list[str]` — sorted by each action's declared `order`
- `unmatched: list[str]` — files that hit no rule
- `fallback_applied: bool` — did the fallback policy contribute anything?

That's the whole API surface. Everything else (loading YAML, glob matching, regex caching) is internal.

### Glob patterns

`**` (zero or more path segments) and `*` (within one segment) are translated to compiled regex once and cached. The translation lives in `_glob_to_regex`. Standard `fnmatch` doesn't handle `**` correctly (it treats it the same as `*`), and `pathlib.PurePath.match` requires constructing a Path per check.

Caching matters: a single decider invocation matches every changed file against every rule pattern. With 50 changed files and 20 rules, that's 1000 match attempts. Compile-once-then-reuse takes the inner loop from microseconds to nanoseconds.

### Fallback

When a file matches no rule, the fallback policy decides:

- `none` (default): unmatched files contribute nothing
- `all`: fire every declared action
- `[action1, action2, ...]`: fire just these

`all` is the safest default for new projects — better to over-restart than to silently skip. `none` makes sense once you have full coverage and want unmatched files to be a signal that the rule set is stale (combined with `--show-unmatched` in CI).

## The import graph (`import_graph.py`)

The decider treats input as a flat list of file paths. That misses transitive impact: changing `utils/db.py` doesn't restart anything if no rule matches `utils/**`, even though half the codebase imports it.

The import graph fixes this. When `--root <path>` is set:

1. Walk every `.py` under `<path>`, skipping `__pycache__`, `.venv`, dotted directories.
2. Parse each file with `ast.parse`.
3. For each `Import` / `ImportFrom` node, resolve the module reference to a file path within the project. Build the graph as `target -> set(importers)`.
4. Given the changed file list, do a BFS in the reverse direction. Every file reachable that way gets added to the seed list.
5. Hand the expanded list to the decider.

### Module resolution

Python's import semantics are loose enough that several syntactic forms can refer to the same file:

```python
import pkg.foo            # → pkg/foo.py
from pkg import foo       # → pkg/foo.py (foo is a submodule)
from pkg.foo import X     # → pkg/foo.py (X is a name inside foo)
```

For each `from base import name`, we try `base.name` first (assuming `name` is a submodule), then fall back to `base` (assuming `name` is a name in `base`'s `__init__.py`). Either way, both the submodule case and the namespace case end up with an edge to the right file — at the cost of an extra index lookup per name.

Star imports `from base import *` resolve only to `base` itself. Tracking which symbols are actually re-exported from a star import would require running the module, which the decider refuses to do on principle (see Pillar 1).

### The src-layout gotcha

This is the one that bit the upstream project for a month before being noticed.

If your project uses src-layout:

```
project/
├── pyproject.toml
└── src/
    └── your_pkg/
        ├── __init__.py
        └── foo.py
```

…then your imports look like `from your_pkg.foo import bar`. The dotted name `your_pkg.foo` resolves to `src/your_pkg/foo.py`.

Run `smart-restart --root .` and the index will key the file as `src.your_pkg.foo`. None of your imports use that dotted name, so no edges get built and the import-chain expansion silently does nothing.

Run `smart-restart --root src` and the index keys it as `your_pkg.foo`, which matches the imports.

The fix in v0.1 is documentation. v0.2 should auto-detect from `[tool.hatch.build.targets.wheel] packages` (or the equivalent for setuptools / poetry).

### Conservative-by-default

When in doubt, restart more rather than less. Specific calls:

- Imports inside functions or `if` blocks are tracked the same as top-level — the function might be called.
- Files with syntax errors contribute no edges (we can't parse them) but don't crash the build.
- Stdlib and third-party imports don't appear in the graph at all (they aren't in the index).

The argument for this conservatism: false positives cost a few seconds of cold start; false negatives cost a 3 a.m. page from a service running stale code.

## What didn't survive extraction

The upstream `_restart_decider.py` had three things that v0.1 deliberately drops:

### Hardcoded action set

```python
VALID_ACTIONS = {"pip_install", "daemon_reload", "restart_brain_mcp"}
```

Replaced by the YAML `actions:` block. No code change needed to add a new service.

### LLM fallback

The upstream calls `claude -p` on unmatched files with a prompt describing the service architecture. It's a clever escape hatch but pulls in a Claude CLI dependency and ties the prompt to the upstream's service shape. v0.1 keeps `smart-restart` dependency-free (just PyYAML). v0.2 will re-cast it as an opt-in plugin.

### `restart_all` as a special case

The upstream treats `restart_all` as a magic fallback that adds `restart_brain_mcp`. v0.1 generalizes this to `fallback: all` (every declared action) or `fallback: [list]`. No more hidden service names.

## Test layout

`tests/test_decider.py` — 25 tests covering glob patterns, rule matching, fallback policies, action ordering.

`tests/test_import_graph.py` — 12 tests using `tmp_path` to build mini Python projects: linear chains, diamonds, relative imports, circular imports, syntax errors, src-layout, stdlib filtering, `__pycache__` skipping.

Every test is hermetic. No filesystem state outside `tmp_path`, no network, no subprocesses. Total runtime is well under one second.

## Open questions for v0.2

- **Auto-detect src-layout** from `pyproject.toml`. Saves users from the most common gotcha.
- **LLM fallback as a plugin.** Inject a callable; the library doesn't ship Claude/OpenAI/whatever. Default to no plugin.
- **Multi-root graphs.** Today users have to invoke twice. The library could accept a list of roots and merge the indices.
- **Watchman / fsmonitor integration?** Probably out of scope; better solved by the consuming script.
- **Symbol-level edges.** `from foo import bar` could distinguish "I depend on the symbol `bar`" from "I depend on all of `foo`." Fine grain helps less than expected (most refactors touch whole files), and the implementation cost is high.
