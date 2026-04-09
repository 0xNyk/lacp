---
name: session-hardening
description: "Production hardening for agent sessions. Includes pretool guards (blocks rm -rf, co-author injection, publishing without approval, data exfiltration), continuous QA (runs tests every N file writes), and session context injection (git state, focus brief, handoff artifacts). Activates automatically via hooks."
---

# Session Hardening

This plugin provides three layers of production hardening:

## Pretool Guard (PreToolUse)

Blocks dangerous operations before they execute:
- `rm -rf` → suggests `trash` instead
- Co-author injection in commits
- `npm/cargo/pip publish` without approval
- `curl | python/node` download-first patterns
- `chmod 777` → suggests specific masks
- `git reset --hard`, `git clean -f`
- Data exfiltration via `curl --data @.env`
- Push to main on public repos

## Continuous QA (PostToolUse)

Runs your project's test command at configurable intervals during work:
- Detects test command from package.json, Makefile, Cargo.toml, pyproject.toml
- Fires every N file writes (default: 10)
- Injects failure feedback without blocking
- Includes thinking prompt on failure (think mode)

## Session Context (SessionStart)

Injects at every session start:
- Git branch, recent commits, modified files
- Focus brief (current problem, beliefs, decisions)
- Handoff artifact from previous session
- System health score
- Self-Memory System context

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `LACP_EVAL_CHECKPOINT_ENABLED` | `0` | Enable continuous QA |
| `LACP_EVAL_CHECKPOINT_INTERVAL` | `10` | Test every N writes |
| `LACP_CONTEXT_MODE` | `` | Active mode (tdd, debugging, sprint, etc.) |
