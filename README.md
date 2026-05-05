# smart-restart

> Rules-as-config restart decider for Python services. Don't restart your whole stack on every git push.

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#status)

## The problem

You ship a small bug fix to one service in your monorepo. Your deploy script restarts everything — bot, API, worker, scheduler — and you eat 30 seconds of cold starts and dropped connections, every time.

Most CI/CD scripts pick between two extremes:

- **Restart everything always** — safe, but wasteful and slow
- **Hand-maintained "if file in dir then restart X"** — fast, but rots silently when imports cross boundaries

`smart-restart` is the middle ground: a small decider that takes the list of changed files and a YAML rule set, then prints which actions are needed. You wire the output into your existing deploy script.

## What it does

```
$ git diff --name-only HEAD~1 HEAD | smart-restart
restart_api
pip_install
```

That's it. It doesn't run the actions — your deploy script does. `smart-restart` just decides.

## Why a separate decider

- **One source of truth** — change `restart-rules.yaml`, every script that consumes the decider stays in sync
- **Composable** — pipe it into bash, Ansible, GitHub Actions, anything that takes stdout
- **Diffable** — your restart rules live in version control, not buried in a deploy script
- **Testable** — pure function, no side effects

## Status

🚧 **Alpha — in active extraction from a private dogfood project (~2 years of daily use).**

v0.1 milestones:
- [ ] Generic rule engine (no project-specific actions hardcoded)
- [ ] Import-chain inference (file A changed → A's importers also restart)
- [ ] Three example configurations: basic / multi-service / monorepo
- [ ] Test suite with fixture projects

See [CHANGELOG.md](CHANGELOG.md) once v0.1.0 ships.

## Install

```bash
pip install smart-restart  # not yet released — coming with v0.1.0
```

## License

[MIT](LICENSE)
