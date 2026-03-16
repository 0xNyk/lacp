# LACP — Local Agent Control Plane

Framework for hardening, orchestrating, and validating Claude Code sessions on local machines.

## Key Directories

| Path | Purpose |
|------|---------|
| `bin/` | CLI commands (`lacp-test`, `lacp-doctor`, `lacp-brain-expand`, etc.) |
| `hooks/` | Claude Code hooks (SessionStart, PostToolUse, Stop) |
| `scripts/lacp-lib.sh` | Shared shell library — sourced by all bin/ commands |
| `scripts/ci/` | CI test scripts (`test-*.sh`) |
| `scripts/runners/` | Pipeline runners (brain-expand steps, etc.) |
| `config/` | Policy files (sandbox, MCP auth, route policy) |
| `dist/` | Distribution/packaging assets |
| `Formula/` | Homebrew formula |

## Running Tests

```bash
# Full suite (~60 tests)
bin/lacp-test

# Quick suite (doctor + route policy)
bin/lacp-test --quick

# Isolated (temporary roots, no side effects)
bin/lacp-test --isolated

# Single test
bash scripts/ci/test-<name>.sh
```

## Conventions

- All bash scripts use `set -euo pipefail`
- All bin/ scripts source `scripts/lacp-lib.sh` for shared functions (`log`, `die`, `require_cmd`, etc.)
- CI tests use `assert_eq` pattern — compare actual vs expected, print PASS/FAIL
- CI tests create temp dirs, `trap cleanup EXIT` — no leftover state
- JSON output via `--json` flag on bin/ commands

## Hook Architecture

Hooks live in `hooks/` and are installed to `~/.claude/` via `bin/lacp-claude-hooks apply-profile`.

| Hook | Event | Purpose |
|------|-------|---------|
| `stop_quality_gate.py` | Stop | Modular Python quality gate with test verification + heuristics + Ollama |
| `session_start.py` | SessionStart | Unified Python hook with git context + test cmd caching |
| `pretool_guard.py` | PreToolUse | Co-author, scp/root, rm -rf, publishing, exfiltration guards |
| `detect_session_changes.py` | (library) | Scans transcript for file changes (imported by stop hook) |
| `hook_telemetry.py` | (library) | JSONL telemetry logger with rotation (imported by stop hook) |
| `write_validate.py` | PostToolUse(Write) | YAML frontmatter schema validation |
| `session_orient.sh` | SessionStart | Vault tree, recent changes (legacy bash) |
| `stop_quality_gate.sh` | Stop | Ollama-backed rationalization detection (legacy bash) |

Profiles: `minimal-stop`, `balanced`, `hardened-exec`, `quality-gate`, `quality-gate-v2`, `orient`, `session-start`, `pretool-guard`, `write-validate`.

## Environment Variables

All configurable via env or `.env` file. Key ones:

- `LACP_AUTOMATION_ROOT` — automation scripts root (default: `~/.lacp/automation`)
- `LACP_KNOWLEDGE_ROOT` — knowledge graph root (default: `~/.lacp/knowledge`)
- `LACP_DRAFTS_ROOT` — article drafts root (default: `~/.lacp/drafts`)
- `LACP_OBSIDIAN_VAULT` — Obsidian vault path (default: `~/obsidian/vault`)
- `LACP_WRITE_VALIDATE_PATHS` — colon-separated paths for write validation
- `LACP_TAXONOMY_PATH` — taxonomy.json location for category validation

## Git Workflow

- Branch from `main` for features: `feat/<name>`
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Run `bin/lacp-test` before pushing
