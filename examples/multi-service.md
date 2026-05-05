# Example: multi-service

Three processes that share utility code. **This is the example that motivates import-chain expansion.**

## Files

- [`multi-service.yaml`](multi-service.yaml) — rules

## Project shape

```
src/
├── lib/
│   ├── auth.py          # imported by api + worker
│   ├── db.py            # imported by api + worker + scheduler? maybe
│   └── models.py        # imported by api + worker
├── api/
│   ├── handlers.py      # imports lib.auth, lib.models
│   └── server.py        # imports api.handlers
├── worker/
│   └── jobs.py          # imports lib.auth, lib.db, lib.models
└── scheduler/
    └── tick.py          # imports nothing under lib
```

The naive rule for `src/lib/**` would be: "restart everything." That's safe but throws away the value of having three separate services.

The clever rule for `src/lib/**` would be: "restart api and worker, but not scheduler — they're the ones that import lib." That works on Tuesday. On Wednesday someone adds `from lib.db import pool` to `scheduler/tick.py` and forgets to update the rule.

The right answer is to delete the `src/lib/**` rule entirely and let the import graph figure it out.

## How the rules read

Look at [`multi-service.yaml`](multi-service.yaml). The rule for `src/lib/**` maps to **no actions** — library code never causes a restart on its own. The right services restart because the deploy script invokes `smart-restart --root src`, which expands `lib/auth.py` to include every file that imports it before rule matching runs.

## Worked example

Suppose this is your diff:

```bash
$ git diff --name-only HEAD~1 HEAD
src/lib/auth.py
docs/security.md
```

Run it through (from your project root, so `--root src` resolves correctly):

```bash
$ git diff --name-only HEAD~1 HEAD \
    | smart-restart -r multi-service.yaml --root src --show-expanded
INFO: import-chain expansion added 3 file(s):
  + src/api/handlers.py
  + src/api/server.py
  + src/worker/jobs.py
restart_api
restart_worker
```

What happened:

1. `smart-restart` parsed every `.py` under `src/` and built an import graph (with `src/` as the path prefix so paths line up with `git diff` output).
2. The graph said `src/api/handlers.py` and `src/worker/jobs.py` import `src/lib/auth.py` directly. `src/api/server.py` imports `src/api/handlers.py` transitively.
3. The expanded changed list became `[src/lib/auth.py, docs/security.md, src/api/handlers.py, src/api/server.py, src/worker/jobs.py]`.
4. Rule matching ran:
   - `src/lib/auth.py` → matched `src/lib/**` → no action (explicitly inert)
   - `docs/security.md` → matched `**/*.md` → no action
   - `src/api/...` (two files) → `restart_api`
   - `src/worker/jobs.py` → `restart_worker`
5. Output: `restart_api`, `restart_worker`. Scheduler stays up.

### Why `--root` is the load-bearing flag

If you run the same command **without** `--root`:

```bash
$ git diff --name-only HEAD~1 HEAD | smart-restart -r multi-service.yaml
$ # exit 0, no output
```

`src/lib/auth.py` matched `src/lib/**` (action list empty). `docs/security.md` matched `**/*.md` (also empty). No unmatched files, fallback never fires. Output: nothing.

This is a **silent miss** — the api and worker need to restart but the script tells your deploy pipeline to do nothing. Stale code keeps running.

You could fix this by replacing `src/lib/** → []` with `src/lib/** → [restart_api, restart_worker]`. That works for two services. It rots the moment someone adds `from lib.auth import ...` to scheduler and forgets to update the rule.

`--root` is what makes the whole shape sustainable: leaf modules don't need to know who imports them, and the rule file never has to encode dependencies that already exist in the source.

## When to use this shape

When:

- Multiple processes share a code tree.
- Some processes depend on parts of the shared tree, others don't.
- You want CI / deploys to restart the minimum set, **and** you don't want to maintain dependency mappings by hand.

If you only have one process, [`basic.md`](basic.md) is simpler. If your processes live in completely separate source trees, see [`monorepo.md`](monorepo.md).
