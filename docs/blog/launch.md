# Stop restarting your whole stack on every git push

Most deploy scripts I've inherited or seen on GitHub do one of two things when a commit lands:

- Restart everything. Safe, slow, and you eat 30 seconds of cold starts on every fix.
- Restart whatever the author thought was relevant when they wrote the script. Faster — until the day someone refactors `utils/db.py`, your worker keeps the old code, and you debug a Heisenbug at 3 a.m.

There's a middle ground that almost nobody has codified, even though most teams reinvent some version of it. I just released [`smart-restart`](https://github.com/zx22413/smart-restart) v0.1.0 — a small Python library extracted from a closed-source personal project that's been running this pattern for ~2 years.

This post is about why the obvious approaches break, what the right shape looks like, and the one bug I shipped at the start that took a month to notice.

## The two extremes, and why both rot

The "restart everything" approach is easy to write and impossible to argue with. It's also wasteful in proportion to how seriously you've taken modularity. If your monorepo has a bot, an API, a worker, and a scheduler, every documentation typo restarts all four. You're paying for separation of concerns and getting none of the operational benefit.

The "hand-edited if-block" approach starts cleaner:

```bash
if echo "$CHANGED_FILES" | grep -q "^src/api/"; then
  systemctl restart api
fi
if echo "$CHANGED_FILES" | grep -q "^src/worker/"; then
  systemctl restart worker
fi
```

This works on Tuesday. On Wednesday you add a `from utils.auth import authenticate` to `worker/jobs.py`, the if-block doesn't know `utils/` exists, and your auth fix doesn't make it into worker. The bash script lies to you and everything looks fine.

The right shape, the one I kept reinventing, has two pieces:

1. A **declarative rule file** that says "files matching this pattern need these actions."
2. A **static import-graph expansion** so changes to a leaf utility correctly propagate to whichever services actually import it.

Neither piece alone is enough. Together they're enough that you don't go back to "restart everything" out of fear.

## What `smart-restart` is, exactly

It's a decider, not an executor. You pipe a list of changed files at it, it prints a list of action names. Your existing deploy script (bash, Ansible, GitHub Actions, whatever) consumes those action names and does the actual work.

```bash
$ git diff --name-only HEAD~1 HEAD | smart-restart -r restart-rules.yaml --root src
restart_api
restart_worker
```

The rule file looks like this:

```yaml
actions:
  restart_api: { order: 20 }
  restart_worker: { order: 20 }
  restart_scheduler: { order: 20 }

rules:
  - pattern: "src/api/**"
    actions: [restart_api]
  - pattern: "src/worker/**"
    actions: [restart_worker]
  - pattern: "src/scheduler/**"
    actions: [restart_scheduler]
  - pattern: "src/lib/**"
    actions: []  # leaf utilities — handled via import-chain expansion
```

The `src/lib/**` rule is the interesting one. It explicitly contributes nothing. The lib is never *itself* a reason to restart anything — it's only relevant via who imports it. With `--root src`, the decider parses every Python file under `src/`, builds an import graph, and walks it in reverse: change `lib/auth.py`, find every file that imports it transitively, expand the changed list, then run the rules.

This means your rule file never has to encode "lib touches api and worker" as a hand-maintained fact. The source already encodes it. The decider reads the source.

## The bug I shipped

The first version of the import graph indexed paths relative to whatever directory you passed as `--root`. So with `--root src`, an importer was tracked as `api/handlers.py` (relative to `src/`), not `src/api/handlers.py` (relative to project root).

That sounds fine until you realize the input — what `git diff --name-only` produces — is project-relative: it gives you `src/lib/auth.py`, not `lib/auth.py`. The seed lookup against the graph silently misses. Expansion runs. It finds nothing. Your script returns no actions. Your deploy pipeline does nothing. You ship stale code and don't notice.

I caught this writing the `multi-service` example in `examples/`. The output didn't match what I'd documented should happen. The fix was straightforward — let `build_graph` accept a `path_prefix` and prepend it to every stored path so seed-lookup paths line up with `git diff` output — but it wouldn't have surfaced without dogfooding the example.

This is one of those bugs that look obvious in hindsight and would have been impossible to find via unit tests alone. The unit tests built fixture projects with `tmp_path` and looked at the graph internally; they had no opinion about how a real consumer would pipe paths in. The integration was the test that mattered.

## What's *not* in v0.1

The closed-source upstream has an LLM fallback for unmatched files: it asks Claude to classify whether a given file imports into the running service, with a prompt that describes the service architecture. It's clever but pulls in a CLI dependency and ties the prompt to one specific project's layout. v0.1 keeps the library dependency-free (just PyYAML). v0.2 will re-cast LLM fallback as an opt-in plugin.

Multi-root monorepo support is also deferred. v0.1 handles it by running the decider once per source root and unioning the actions in a small bash wrapper — see [`examples/monorepo.md`](https://github.com/zx22413/smart-restart/blob/main/examples/monorepo.md). v0.2 will probably take multiple `--root` flags directly.

Auto-detection of src-layout from `pyproject.toml` is the gotcha most likely to bite first-time users. v0.1 documents the workaround (pass `--root src`); v0.2 should detect it.

## Try it

```bash
pip install smart-restart
```

There's a quick start in the [README](https://github.com/zx22413/smart-restart) and three worked examples covering the common shapes:

- [`basic`](https://github.com/zx22413/smart-restart/blob/main/examples/basic.md) — one service
- [`multi-service`](https://github.com/zx22413/smart-restart/blob/main/examples/multi-service.md) — shared lib, multiple consumers
- [`monorepo`](https://github.com/zx22413/smart-restart/blob/main/examples/monorepo.md) — independent source trees

If you've been hand-editing restart logic in your deploy script for years, this might save you the next outage. If you've been restarting everything because you couldn't be bothered to figure out the dependencies, this might let you stop.

The whole library is under 700 lines, MIT-licensed, and tested against Python 3.11 / 3.12 / 3.13 on Linux. The [GitHub repo](https://github.com/zx22413/smart-restart) has the source, issues, and the architecture document if you want to read about the design choices in more depth.
