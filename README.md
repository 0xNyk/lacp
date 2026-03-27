<div align="center">

# LACP

**Control-plane-grade agent harness for Claude, Codex & Hermes.**

LACP is a harness-first execution framework with policy-gated operations, verification/evidence loops, 5-layer memory, and auditable agent workflows — all local-first, zero external dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stable](https://img.shields.io/badge/Status-stable%20v0.3.x-brightgreen)](https://github.com/0xNyk/lacp/releases)
[![Shell](https://img.shields.io/badge/Shell-bash%20%2B%20python3-blue)](https://github.com/0xNyk/lacp)

![LACP Banner](docs/assets/readme-banner.png)

</div>

---

> **Stable Release** — LACP is stable for daily local-first operations. Defaults, command contracts, and core workflows are backward-compatible. If something regresses, [open an issue](https://github.com/0xNyk/lacp/issues).

## Contents

- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Install Options](#install-options)
- [Who It's For](#who-its-for)
- [Testing](#testing)
- [Security](#security)
- [Contributing](#contributing)

### What LACP is (by harness definition)

LACP is an **agent harness** with **control-plane governance**:
- **Harness layer:** tasks, verification contracts, evidence manifests, replayable run loops
- **Control-plane layer:** risk tiers, budget gates, context/session contracts, approvals, provenance

This keeps the core value clear: not just generating output, but producing **auditable, policy-compliant outcomes**.

<table>
<tr><td><b>Policy gates</b></td><td>Risk tiers (safe/review/critical), budget ceilings, context contracts, and session fingerprints — every agent invocation is gated and auditable.</td></tr>
<tr><td><b>5-layer memory</b></td><td>Session memory, Obsidian knowledge graph, ingestion pipeline, code intelligence (GitNexus), and agent identity with hash-chained provenance.</td></tr>
<tr><td><b>Hook pipeline</b></td><td>Modular Python hooks for Claude Code — session context injection, pretool guards, write validation, and stop quality gates with local LLM eval.</td></tr>
<tr><td><b>Obsidian brain</b></td><td>First-class vault management, mycelium-inspired memory consolidation, QMD indexing, and config-as-code with auto-optimization.</td></tr>
<tr><td><b>Multi-agent orchestration</b></td><td>dmux/tmux session management, git worktree isolation, swarm workflows, and Claude native worktree backend.</td></tr>
<tr><td><b>Local-first security</b></td><td>Zero external CI by default, no secrets in config, environment-driven credentials, TTL approval tokens for remote execution.</td></tr>
<tr><td><b>Execution tiers</b></td><td>trusted_local, local_sandbox, and remote_sandbox (Daytona/E2B) with policy-driven routing and provider override.</td></tr>
<tr><td><b>Evidence pipelines</b></td><td>Browser e2e, API e2e, smart-contract e2e harnesses with manifest evidence, auth checks, and PR preflight gates.</td></tr>
</table>

---

## Quick Start

### Install

```bash
# Homebrew (recommended)
brew tap 0xNyk/lacp && brew install lacp

# or cURL bootstrap
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

### Bootstrap & Verify

```bash
lacp bootstrap-system --profile starter --with-verify
lacp doctor --json | jq '.ok,.summary'
```

After bootstrap: `.env` is created, dependencies installed, directories scaffolded, Obsidian vault wired, and verification artifacts produced.

For the full setup and daily operator flow, start with the [Runbook](docs/runbook.md) and [Local Dev Loop](docs/local-dev-loop.md).

### First Gated Command

```bash
# Route a task through LACP policy gates
lacp run --task "hello world" --repo-trust trusted -- echo "LACP is working"

# Make claude/codex/hermes default to LACP routing (reversible)
lacp adopt-local --json | jq
```

---

## Documentation

| Guide | What You'll Learn |
|-------|-------------------|
| [Runbook](docs/runbook.md) | Daily operator workflow, command map, troubleshooting entry points |
| [Local Dev Loop](docs/local-dev-loop.md) | Fast build/test/verify loop for contributors |
| [Framework Scope](docs/framework-scope.md) | What LACP is, what it is not, and design boundaries |
| [Implementation Path](docs/implementation-path-2026.md) | Step-by-step rollout plan for full harness adoption |
| [Memory Quality Workflow](docs/memory-quality-workflow.md) | How memory ingestion, expansion, and validation are run safely |
| [Incident Response](docs/incident-response.md) | Triage and recovery flow when policy gates fail |
| [Release Checklist](docs/release-checklist.md) | Pre-release, release, and post-release controls |
| [Troubleshooting](docs/troubleshooting.md) | Common errors, doctor diagnostics, fix hints |

### Project health files

- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution and PR expectations
- [SECURITY.md](SECURITY.md) — vulnerability disclosure process
- [CHANGELOG.md](CHANGELOG.md) — release history
- [LICENSE](LICENSE) — MIT

---

## Architecture

```
lacp/
├── bin/                    # CLI commands (lacp <command>)
│   ├── lacp                # Top-level dispatcher
│   ├── lacp-bootstrap-system
│   ├── lacp-doctor         # Diagnostics (--json, --fix-hints)
│   ├── lacp-route          # Policy-driven tier/provider routing
│   ├── lacp-sandbox-run    # Gated execution with artifact logging
│   ├── lacp-brain-*        # Memory stack (ingest, expand, doctor, stack)
│   ├── lacp-obsidian       # Vault config management
│   ├── lacp-up             # Multi-instance agent sessions
│   ├── lacp-swarm          # Batch orchestration
│   └── lacp-claude-hooks   # Hook profile management
├── config/
│   ├── sandbox-policy.json     # Routing + cost ceilings
│   ├── risk-policy-contract.json
│   ├── obsidian/               # Vault manifest + optimization profiles
│   └── harness/                # Task schemas, sandbox profiles, verification policies
├── hooks/                  # Python hook pipeline for Claude Code
├── scripts/
│   ├── ci/                 # Test suites
│   └── runners/            # Daytona/E2B execution adapters
└── docs/                   # Guides and reference docs
```

### Control Flow

```
Agent invocation
  → lacp route (risk tier + provider selection)
    → context contract validation
      → budget gate check
        → session fingerprint verification
          → sandbox-run (dispatch + artifact logging)
```

## Features

### Policy-Gated Execution

Every command routes through risk tiers (`safe` → `review` → `critical`), budget ceilings per tier, and context contracts that validate host, working directory, git branch, and remote targets before execution.

### 5-Layer Memory Stack

| Layer | Purpose |
|-------|---------|
| **Session memory** | Per-project scaffolding under `~/.claude/projects/` |
| **Knowledge graph** | Obsidian vault with MCP wiring (smart-connections, QMD, ori-mnemos) |
| **Ingestion pipeline** | `brain-ingest` converts text/audio/video/URLs into structured notes |
| **Code intelligence** | GitNexus AST-level knowledge graph via MCP (optional) |
| **Agent identity** | Persistent IDs per (hostname, project) + SHA-256 hash-chained provenance |

```bash
lacp brain-stack init --json | jq          # Bootstrap all layers
lacp brain-ingest --url "https://..." --apply --json | jq
lacp brain-expand --apply --json | jq      # Full expansion loop
```

### Hook Pipeline for Claude Code

Modular Python hooks enforcing quality at every session stage:

| Hook | Event | Purpose |
|------|-------|---------|
| `session_start.py` | SessionStart | Git context injection, test command caching |
| `pretool_guard.py` | PreToolUse | Block dangerous operations (publish, `chmod 777`, fork bombs, secrets) |
| `write_validate.py` | PostToolUse | YAML frontmatter schema validation |
| `stop_quality_gate.py` | Stop | 3-tier eval: heuristics, test verification, local LLM rationalization detection |

Profiles: `minimal-stop`, `balanced`, `hardened-exec`, `quality-gate-v2`. Apply with `lacp claude-hooks apply-profile <profile>`.

### Mycelium Network Memory

Biologically-inspired memory consolidation modeled on fungal networks:

| Mechanism | Description |
|-----------|-------------|
| Adaptive path reinforcement | Frequently-traversed edges strengthen (like mycelium hyphae) |
| Self-healing | Pruned nodes trigger reconnection of orphaned neighbors |
| Exploratory tendrils | Frontier nodes in active categories shielded from pruning |
| Flow scoring | Betweenness centrality identifies critical knowledge hubs |
| Temporal decay | FSRS dual-strength model with forgetting curve |

### Multi-Agent Orchestration

```bash
# dmux-style multi-instance launch
lacp up --session dev --instances 3 --command "claude"

# Git worktree isolation
lacp worktree create --repo-root . --name "feature-a" --base HEAD

# Batch swarm execution
lacp swarm launch --manifest ./swarm.json
```

### Evidence Pipelines

Generate machine-verifiable evidence for PR gates:

```bash
lacp e2e smoke --workdir . --init-template --command "npx playwright test --grep @smoke"
lacp api-e2e smoke --workdir . --init-template --command "npx schemathesis run --checks all"
lacp contract-e2e smoke --workdir . --init-template --command "forge test -vv"
lacp pr-preflight --changed-files ./changed-files.txt --checks-json ./checks.json
```

---

## Prerequisites

| Required | Recommended |
|----------|-------------|
| `bash`, `python3`, `jq`, `rg` (ripgrep) | `shellcheck`, `tmux`, `gh` |

The installer auto-detects and installs missing dependencies on macOS via Homebrew.

## Install Options

<details>
<summary><strong>All installation methods</strong></summary>

### Homebrew

```bash
brew tap 0xNyk/lacp
brew install lacp            # stable v0.3.0
brew install --HEAD lacp     # track main branch
```

### cURL Bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

### Verified Release (recommended for production)

```bash
VERSION="0.3.0"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/lacp-${VERSION}.tar.gz"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/SHA256SUMS"
grep "lacp-${VERSION}.tar.gz" SHA256SUMS | shasum -a 256 -c -
tar -xzf "lacp-${VERSION}.tar.gz" && cd "lacp-${VERSION}"
bin/lacp-install --profile starter --with-verify
```

</details>

## Who It's For

LACP is for developers who want **measurable, policy-gated, reproducible** local agent operations with explicit pass/fail gates and artifact-backed records.

LACP is **not** for users looking for a chat UI, managed cloud orchestration, or who don't want to maintain local scripts/config.

## Testing

```bash
lacp test --quick       # Fast smoke tests
lacp test --isolated    # Full isolated suite
lacp doctor --json      # Structured diagnostics
lacp posture --strict   # Policy compliance check
```

<details>
<summary><strong>Individual test suites</strong></summary>

```bash
scripts/ci/test-route-policy.sh
scripts/ci/test-mode-and-gates.sh
scripts/ci/test-knowledge-doctor.sh
scripts/ci/test-ops-commands.sh
scripts/ci/test-install.sh
scripts/ci/test-system-health.sh
scripts/ci/test-obsidian-cli.sh
scripts/ci/test-brain-memory.sh
scripts/ci/smoke.sh
```

</details>

<details>
<summary><strong>Command reference</strong></summary>

### Core

| Command | Purpose |
|---------|---------|
| `lacp bootstrap-system` | One-command install + onboard + verify |
| `lacp doctor` | Structured diagnostics (`--json`, `--fix-hints`, `--check-limits`) |
| `lacp status` | Current operating state snapshot |
| `lacp mode` | Switch local-only / remote-enabled |
| `lacp run` | Single gated command execution |
| `lacp loop` | Intent → execute → observe → adapt control loop |
| `lacp test` | Local test suite (`--quick`, `--isolated`) |

### Memory & Knowledge

| Command | Purpose |
|---------|---------|
| `lacp brain-stack` | Initialize/audit 5-layer memory stack |
| `lacp brain-ingest` | Ingest text/audio/video/URLs into Obsidian |
| `lacp brain-expand` | Full brain expansion loop |
| `lacp brain-doctor` | Brain ecosystem health checks |
| `lacp obsidian` | Vault config management (audit/apply/optimize) |
| `lacp repo-research-sync` | Mirror repo research into knowledge graph |

### Orchestration

| Command | Purpose |
|---------|---------|
| `lacp up` | dmux-style multi-instance launch |
| `lacp orchestrate` | dmux/tmux/worktree orchestration adapter |
| `lacp worktree` | Git worktree lifecycle management |
| `lacp swarm` | Batch swarm workflow (plan/launch/status) |
| `lacp adopt-local` | Install LACP routing wrappers for claude/codex |

### Security & Policy

| Command | Purpose |
|---------|---------|
| `lacp route` | Deterministic tier/provider routing |
| `lacp sandbox-run` | Gated execution with artifact logging |
| `lacp policy-pack` | Apply policy baselines (starter/strict/enterprise) |
| `lacp claude-hooks` | Audit/repair/optimize hook profiles |
| `lacp security-hygiene` | Secret/path/workflow/.env scan |
| `lacp pr-preflight` | PR policy gate evaluation |

### Release & Evidence

| Command | Purpose |
|---------|---------|
| `lacp release-prepare` | Pre-live discipline (gate + canary + status) |
| `lacp release-verify` | Release verification (checksum + archive + brew) |
| `lacp e2e` | Browser e2e evidence pipeline |
| `lacp api-e2e` | API/backend e2e evidence pipeline |
| `lacp contract-e2e` | Smart-contract e2e evidence pipeline |
| `lacp canary` | 7-day promotion gate over retrieval benchmarks |

### Utilities

| Command | Purpose |
|---------|---------|
| `lacp console` | Interactive slash-command shell |
| `lacp time` | Project/client session time tracking |
| `lacp agent-id` | Persistent agent identity registry |
| `lacp provenance` | Cryptographic session provenance chain |
| `lacp context-profile` | Reusable context contract templates |
| `lacp vendor-watch` | Monitor Claude/Codex version drift |
| `lacp system-health` | macOS/Apple Silicon workstation readiness |
| `lacp mcp-health` | Probe all configured MCP servers |

</details>

## Security

- No secrets in repo config — environment-driven via `.env`
- Zero external CI by default (`LACP_NO_EXTERNAL_CI=true`)
- Remote execution disabled by default (`LACP_ALLOW_EXTERNAL_REMOTE=false`)
- Risk-tier gating with TTL approval tokens
- Structured input contracts for risky runs
- Artifact logs for auditable execution history
- See [SECURITY.md](SECURITY.md) for vulnerability reporting

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

If you find this project useful, consider supporting the open-source work:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-orange?logo=buymeacoffee)](https://buymeacoffee.com/nyk_builderz)

**Solana:** `BYLu8XD8hGDUtdRBWpGWu5HKoiPrWqCxYFSh4oxXuvPg`


---

<div align="center">

**Need agent infrastructure, trading systems, or Solana applications built for your team?**

[Builderz](https://builderz.dev) ships production AI systems — 32+ products across 15 countries.

[Get in touch](https://builderz.dev) | [@nyk_builderz](https://x.com/nyk_builderz)

</div>

## License

[MIT](LICENSE) © 2026 [0xNyk](https://github.com/0xNyk)
