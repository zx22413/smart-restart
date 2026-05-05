# Examples

Three configurations covering the common deployment shapes. Read in order:

| Example | Pattern | Use when |
|---------|---------|----------|
| [`basic`](basic.md) | one process, one rule set | a single service that owns its tree |
| [`multi-service`](multi-service.md) | multiple processes share a code tree, import-chain expansion drives restarts | shared `lib/` imported by some services but not others |
| [`monorepo`](monorepo.md) | independent source trees, one decider invocation per tree | multiple services with their own `pyproject.toml` |

Each markdown file is self-contained: it shows the rule file, walks through a representative diff, and explains why the rules are shaped the way they are.

## Running the examples locally

The `multi-service` walk-through uses a small fixture project; you can build it yourself:

```bash
mkdir -p demo/src/{lib,api,worker,scheduler}
touch demo/src/{lib,api,worker,scheduler}/__init__.py
echo "def authenticate(token): return True" > demo/src/lib/auth.py
echo "from lib.auth import authenticate" > demo/src/api/handlers.py
echo "from api.handlers import authenticate" > demo/src/api/server.py
echo "from lib.auth import authenticate" > demo/src/worker/jobs.py
echo "import time" > demo/src/scheduler/tick.py
cp examples/multi-service.yaml demo/

cd demo
echo "src/lib/auth.py" | smart-restart -r multi-service.yaml --root src --show-expanded
```

Expected output:

```
INFO: import-chain expansion added 3 file(s):
  + src/api/handlers.py
  + src/api/server.py
  + src/worker/jobs.py
restart_api
restart_worker
```

Scheduler doesn't restart because nothing under `src/scheduler/` imports `lib/auth`.
