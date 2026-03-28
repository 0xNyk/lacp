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
| `stop_quality_gate.py` | Stop | Criteria-based scoring (4 dimensions, weighted avg) + test verification + heuristics + handoff artifact generation |
| `session_start.py` | SessionStart | Git context + test cmd caching + focus brief + handoff injection + stale contract cleanup |
| `eval_checkpoint.py` | PostToolUse(Write/Edit) | Continuous QA — runs tests at intervals during work, injects feedback on failure |
| `pretool_guard.py` | PreToolUse | Co-author, scp/root, rm -rf, publishing, exfiltration guards |
| `thinking_nudge.py` | UserPromptSubmit | Nudges user to state position before asking questions (opt-in) |
| `detect_session_changes.py` | (library) | Scans transcript for file changes (imported by stop hook) |
| `hook_telemetry.py` | (library) | JSONL telemetry logger with rotation (imported by stop hook) |
| `hook_contracts.py` | (library) | Typed state exchange between hooks (SessionStartOutput, SprintContract, EvalCheckpoint, HandoffArtifact) |
| `write_validate.py` | PostToolUse(Write) | YAML frontmatter schema validation |
| `session_orient.sh` | SessionStart | Vault tree, recent changes (legacy bash) |
| `stop_quality_gate.sh` | Stop | Ollama-backed rationalization detection (legacy bash) |

Profiles: `minimal-stop`, `balanced`, `hardened-exec`, `quality-gate`, `quality-gate-v2`, `orient`, `session-start`, `pretool-guard`, `write-validate`, `thinking-partner`.

## Context Modes

Set `LACP_CONTEXT_MODE` to activate a mode (injected at session start):

| Mode | Purpose |
|------|---------|
| `brainstorm` | Design exploration before implementation (no code until design approved) |
| `debugging` | 4-phase systematic root cause investigation |
| `handoff-resume` | Continue from previous session handoff artifact |
| `implementation` | Focused implementation partner |
| `review` | Code review mode |
| `sprint` | Pre-agreed completion criteria (sprint contracts) |
| `tdd` | Strict RED-GREEN-REFACTOR discipline |
| `thinking-partner` | Challenge assumptions, surface blind spots |
| `verification` | Evidence-before-claims discipline |

## CLI Stream

`lacp` (no args) launches a hardened agent session:

```bash
lacp                              # auto-detects claude/codex/hermes/opencode/gemini/goose/aider/openclaw
lacp --mode tdd                   # TDD mode with eval checkpoints
lacp --mode debugging             # systematic debugging mode
lacp --resume                     # continue last session
lacp "fix the auth bug"           # one-shot prompt
lacp watch --follow               # live telemetry stream
lacp watch --summary              # session health overview
lacp handoff show                 # view handoff artifact for current dir
lacp scaffold-audit               # identify removable pipeline stages
```

## Environment Variables

All configurable via env or `.env` file. Key ones:

- `LACP_AUTOMATION_ROOT` — automation scripts root (default: `~/.lacp/automation`)
- `LACP_KNOWLEDGE_ROOT` — knowledge graph root (default: `~/.lacp/knowledge`)
- `LACP_DRAFTS_ROOT` — article drafts root (default: `~/.lacp/drafts`)
- `LACP_OBSIDIAN_VAULT` — Obsidian vault path (default: `~/obsidian/vault`)
- `LACP_WRITE_VALIDATE_PATHS` — colon-separated paths for write validation
- `LACP_TAXONOMY_PATH` — taxonomy.json location for category validation
- `LACP_CONTEXT_MODE` — active context mode (tdd, debugging, sprint, etc.)
- `LACP_EVAL_CHECKPOINT_ENABLED` — enable continuous QA during work (default: `0`)
- `LACP_EVAL_CHECKPOINT_INTERVAL` — run tests every N file writes (default: `10`)
- `LACP_QUALITY_GATE_THRESHOLD` — criteria scoring threshold 1-5 (default: `2.5`)
- `LACP_BLIND_SPOT_ENABLED` — enable blind spot reflection at session end (default: `0`)

> Full list of 40+ environment variables with defaults: `config/lacp.env.example`

## Self-Memory System (SMS)

Psychology-informed agent memory based on Conway's Self-Memory System (2005).

Five principles implemented:
1. **Hierarchical temporal** — episodes grouped into epochs (life periods)
2. **Goal-relevant filtering** — focus brief gates memory retrieval
3. **Emotional weighting** — significance scoring (0-1) biases recall
4. **Narrative coherence** — agent story arc across sessions
5. **Co-emergent self-model** — identity ↔ memory feedback loop

```bash
lacp sms context           # what SMS injects at session start
lacp sms episodes          # recorded episodes with significance
lacp sms significance      # significance distribution
lacp sms synthesize        # create epoch from recent episodes
lacp sms narrative         # view/update agent narrative
lacp sms self-model        # view/update evolving self-model
```

Core module: `hooks/self_memory_system.py`
Data: `~/.lacp/sms/` (episodes.jsonl, epochs.jsonl, narrative.json, self-model.json)

## Git Workflow

- Branch from `main` for features: `feat/<name>`
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Run `bin/lacp-test` before pushing

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **lacp** (264 symbols, 453 relationships, 13 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/lacp/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/lacp/context` | Codebase overview, check index freshness |
| `gitnexus://repo/lacp/clusters` | All functional areas |
| `gitnexus://repo/lacp/processes` | All execution flows |
| `gitnexus://repo/lacp/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
