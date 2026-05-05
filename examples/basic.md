# Example: basic

A single web service with dependencies. The simplest useful configuration.

## Files

- [`basic.yaml`](basic.yaml) — rules

## What this configures

- Two actions: `pip_install` (runs first) and `restart_api`.
- Touching `requirements.txt` or `pyproject.toml` reinstalls deps and restarts the api.
- Touching anything under `src/` restarts the api (no reinstall).
- Markdown changes are explicitly inert.
- Anything else (config files you forgot to write a rule for, etc.) triggers the fallback: restart the api, just to be safe.

## Try it

Save this as `basic.yaml` and pipe a diff at it:

```bash
$ printf 'src/api.py\nREADME.md\nrequirements.txt\nconfig.toml\n' \
    | smart-restart -r basic.yaml --show-unmatched
INFO: 1 unmatched file(s):
  - config.toml
INFO: fallback policy applied
pip_install
restart_api
```

What happened, line by line:

| Input | Matched rule | Contributes |
|-------|--------------|-------------|
| `src/api.py` | `src/**` | `restart_api` |
| `README.md` | `**/*.md` | nothing (rule is `actions: []`) |
| `requirements.txt` | `requirements.txt` | `pip_install`, `restart_api` |
| `config.toml` | none | fallback `[restart_api]` fires |

The output is sorted by each action's declared `order`, so `pip_install` (order 10) prints before `restart_api` (order 20). Your deploy script consumes those lines in order.

## When this is enough

Use this shape when:

- You have one process to restart.
- You're happy treating the whole `src/` tree as one unit.
- You don't have a layered codebase where leaf utilities are imported by many modules.

If a leaf utility changes, the rule above already restarts the api (because `src/**` matches), so you don't need import-chain expansion. See [`multi-service.md`](multi-service.md) for the case where you do.
