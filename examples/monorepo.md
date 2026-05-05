# Example: monorepo

Multiple services in **separate source trees**. v0.1 supports one root per invocation, so the pattern is "run twice and union."

## Project shape

```
project/
├── services/
│   ├── api/
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── api/...        # FastAPI service
│   └── worker/
│       ├── pyproject.toml
│       └── src/
│           └── worker/...     # background worker
└── shared/
    └── common/
        └── src/
            └── common/...     # imported by both via path / git submodule / vendored
```

Each service has its own `pyproject.toml` and its own import root (`services/api/src`, `services/worker/src`). The decider can only build one graph at a time, so we run it once per service and merge the action sets.

## Per-service rules

Each service ships its own rules file:

```yaml
# services/api/restart-rules.yaml
actions:
  restart_api: { order: 20 }

rules:
  - pattern: "api/**"
    actions: [restart_api]
  - pattern: "**/*.md"
    actions: []

fallback: [restart_api]
```

```yaml
# services/worker/restart-rules.yaml
actions:
  restart_worker: { order: 20 }

rules:
  - pattern: "worker/**"
    actions: [restart_worker]
  - pattern: "**/*.md"
    actions: []

fallback: [restart_worker]
```

## Running them

A small bash wrapper:

```bash
#!/usr/bin/env bash
# decide.sh — run smart-restart per service and union the actions.
set -euo pipefail

DIFF=$(git diff --name-only HEAD~1 HEAD)

api_changes=$(echo "$DIFF" | grep -E '^services/api/|^shared/' || true)
worker_changes=$(echo "$DIFF" | grep -E '^services/worker/|^shared/' || true)

# Strip the service prefix so paths are root-relative for each invocation.
api_actions=$(
  echo "$api_changes" | sed 's|^services/api/||; s|^shared/common/|common/|' \
    | smart-restart -r services/api/restart-rules.yaml --root services/api/src
)

worker_actions=$(
  echo "$worker_changes" | sed 's|^services/worker/||; s|^shared/common/|common/|' \
    | smart-restart -r services/worker/restart-rules.yaml --root services/worker/src
)

# Union. Order is preserved within each invocation; cross-service order is
# whatever you want it to be (here: api first, then worker).
{ echo "$api_actions"; echo "$worker_actions"; } | awk 'NF && !seen[$0]++'
```

The two filtering greps are the part that needs care: each invocation should only see paths relevant to its service. `shared/` belongs to both.

## Why not just one big root?

You can't, in general. Two reasons:

- **Different package namespaces.** `services/api/src/api/foo.py` and `services/worker/src/worker/foo.py` resolve their imports against different roots. A single `--root project/` would build a graph keyed by `services.api.src.api.foo` — which no real import statement ever produces.
- **Different requirements.** Each service has its own `pyproject.toml`. Lumping them means a change to either reinstalls both.

The right answer is one decider invocation per service. If your monorepo is small (say, three services), the bash above is fine. If it's larger, you'll want a real orchestrator (`bazel run //services/...:restart_decision` style) and `smart-restart` becomes the per-service primitive inside it.

## v0.2 might change this

v0.2 will probably accept multiple `--root` flags and merge the indices, which would let one invocation handle the whole monorepo. The bash wrapper would still work — but the interface inside it would simplify.

Until then: one decider per service, union the outputs.
