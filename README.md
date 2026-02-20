# LACP

[![CI](https://github.com/0xNyk/lacp/actions/workflows/ci.yml/badge.svg)](https://github.com/0xNyk/lacp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local Agent Control Plane for Claude/Codex.

Status: active development (`v0.1.x`).

LACP turns local agent operations into an auditable system with:
- reproducible onboarding
- verification gates
- policy-based sandbox routing
- artifact-backed health and execution records

LACP is **not** a new runtime. It is a control plane around your existing local automation and agent tooling.

## Table of Contents

- [End Goal](#end-goal)
- [Prerequisites](#prerequisites)
- [Architecture](#architecture)
- [Execution Tiers](#execution-tiers)
- [Risk Tiers](#risk-tiers)
- [Budget Gates](#budget-gates)
- [Quick Start](#quick-start)
- [Install Options](#install-options)
- [Who It Is For](#who-it-is-for)
- [What Install Does](#what-install-does)
- [5 Minute Smoke Test](#5-minute-smoke-test)
- [Remote Setup](#remote-setup)
- [Command Reference](#command-reference)
- [Security Model](#security-model)
- [Artifacts](#artifacts)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Optimization Backlog](#optimization-backlog)

## End Goal

Make Claude/Codex operations:
- measurable (benchmarks, snapshots, diagnostics)
- reliable (verification loops, explicit pass/fail gates)
- safe (tiered execution with sandbox policy)
- reproducible (one-command setup and runbook workflows)

## Prerequisites

Required:
- `bash`
- `python3`
- `jq`
- `rg` (`ripgrep`)

Recommended:
- `shellcheck`

## Architecture

### Control-Plane Layer
- `bin/lacp-install`
- `bin/lacp-onboard`
- `bin/lacp-bootstrap`
- `bin/lacp-verify`
- `bin/lacp-doctor`
- `bin/lacp-mode`
- `bin/lacp-status-report`

### Policy + Routing Layer
- policy contract: `config/sandbox-policy.json`
- route decision engine: `bin/lacp-route`
- execution adapter: `bin/lacp-sandbox-run`

### Remote Provider Layer
- setup helper: `bin/lacp-remote-setup`
- remote smoke helper: `bin/lacp-remote-smoke`
- Daytona runner: `scripts/runners/daytona-runner.sh`
- E2B runner: `scripts/runners/e2b-runner.sh`

## Execution Tiers

- `trusted_local`: known low-risk tasks
- `local_sandbox`: semi-trusted work requiring isolation
- `remote_sandbox`: high-risk/high-compute/long-running tasks

For remote routes, provider is policy-driven (`daytona` or `e2b`), with override support.

## Risk Tiers

- `safe`: executes without approval gate
- `review`: requires valid TTL approval token (`bin/lacp-mode remote-enabled --ttl-min <N>`)
- `critical`: always requires explicit per-run confirmation (`--confirm-critical true`)

## Budget Gates

- Per-tier cost ceilings are configured in `config/sandbox-policy.json` under `routing.cost_ceiling_usd_by_risk_tier`.
- Pass `--estimated-cost-usd <N>` to `bin/lacp-sandbox-run`.
- If estimate exceeds the tier ceiling, run is blocked unless `--confirm-budget true` is explicitly provided.

## Quick Start

```bash
cd ~/control/frameworks/lacp
bin/lacp-install --profile starter --with-verify
bin/lacp-mode show
bin/lacp-mode remote-enabled --ttl-min 30
bin/lacp-doctor
bin/lacp-verify --hours 24
```

## Install Options

### Homebrew (HEAD from this repo)

```bash
brew tap 0xNyk/lacp
brew install --HEAD lacp
```

### cURL bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

Optional flags:

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash -s -- \
  --ref main \
  --profile starter \
  --with-verify true
```

## Who It Is For

Use LACP if you want:
- measurable local agent operations (artifacts + diagnostics)
- policy-based execution gates (risk, approvals, budget)
- repeatable onboarding for Claude/Codex workflows

LACP is not for:
- users looking for a chat UI product
- users who do not want to maintain local scripts/config
- teams that need managed cloud orchestration out of the box

## What Install Does

`bin/lacp-install --profile starter --with-verify`:
- creates `.env` from template when missing
- ensures required root/data paths exist
- scaffolds safe starter automation scripts when missing
- runs onboarding preflight checks
- runs verification and produces baseline artifacts

## 5 Minute Smoke Test

```bash
cd ~/control/frameworks/lacp
bin/lacp-install --profile starter --with-verify
bin/lacp-test --quick
bin/lacp-doctor --json | jq '.ok,.summary'
bin/lacp-status-report --json | jq
```

Expected:
- `lacp-test --quick` exits `0`
- doctor reports `"ok": true`
- status report includes mode + doctor + artifact fields

## Remote Setup

By default, LACP runs in **zero-external mode**:
- `LACP_ALLOW_EXTERNAL_REMOTE="false"`
- `LACP_REMOTE_APPROVAL_TTL_MIN="30"` (used when granting remote approval)
- remote routes can still be planned/tested via `--dry-run`
- live remote execution is blocked unless explicitly enabled **and** approval is still within TTL

### Daytona

```bash
cd ~/control/frameworks/lacp
bin/lacp-remote-setup --provider daytona
daytona login
bin/lacp-remote-smoke --provider daytona --json
```

### E2B

```bash
cd ~/control/frameworks/lacp
bin/lacp-remote-setup --provider e2b --e2b-sandbox-id "<running-sandbox-id>"
bin/lacp-remote-smoke --provider e2b --json
```

Notes:
- Default mode is non-interactive lifecycle (`create -> exec -> kill`) using E2B SDK.
- `E2B_SANDBOX_ID` enables existing-sandbox mode via e2b CLI.

## Command Reference

- `bin/lacp-onboard`: initialize `.env`, run bootstrap, optional full verify
- `bin/lacp-install`: first-time installer (creates roots, starter stubs, then onboard)
- `bin/lacp-test`: one-command local test suite (`--quick` supported)
- `bin/lacp-bootstrap`: hard preflight (paths, scripts, policy file)
- `bin/lacp-verify`: memory pipeline + retrieval gates + snapshot + trend refresh
- `bin/lacp-doctor`: structured diagnostics (`--json` supported)
- `bin/lacp-knowledge-doctor`: markdown knowledge graph quality gates (`--json` supported)
- `bin/lacp-mode`: switch/read operating mode (`local-only` vs `remote-enabled`)
- `bin/lacp-mode revoke-approval`: revoke remote approval token immediately
- `bin/lacp-status-report`: generate compact system snapshot (`docs/system-status.md`)
- `bin/lacp-route`: deterministic tier/provider routing with reasons
- `bin/lacp-sandbox-run`: route + risk-tier/budget gates + dispatch + execution artifact logging
- `bin/lacp-remote-setup`: provider onboarding and config wiring
- `bin/lacp-remote-smoke`: provider-aware smoke test with artifact output

## Security Model

- No secrets in repo configuration files
- Environment-driven configuration in `.env`
- Policy-driven remote routing
- External remote execution disabled by default (`LACP_ALLOW_EXTERNAL_REMOTE=false`)
- Risk-tier gating (`safe/review/critical`) with TTL and per-run confirmation controls
- Explicit runner guardrails for remote execution
- Artifact logs for auditable runs

See:
- `docs/framework-scope.md`
- `docs/runbook.md`
- `CONTRIBUTING.md`
- `SECURITY.md`

## Artifacts

- benchmark reports: `~/control/knowledge/knowledge-memory/data/benchmarks/*.json`
- snapshots: `~/control/automation/ai-dev-optimization/data/snapshots/*.json`
- sandbox runs: `~/control/knowledge/knowledge-memory/data/sandbox-runs/*.json`
- remote smoke runs: `~/control/knowledge/knowledge-memory/data/remote-smoke/*.json`

## Testing

```bash
cd ~/control/frameworks/lacp
./scripts/ci/test-route-policy.sh
./scripts/ci/test-mode-and-gates.sh
./scripts/ci/test-knowledge-doctor.sh
./scripts/ci/test-install.sh
./scripts/ci/smoke.sh
```

Or use:

```bash
bin/lacp-test
bin/lacp-test --quick
```

## Troubleshooting

- `bootstrap failed missing script`: run `bin/lacp-install --profile starter --force-scaffold`
- remote `exit_code=8`: run `bin/lacp-mode remote-enabled --ttl-min 30`
- budget `exit_code=10`: lower `--estimated-cost-usd` or pass `--confirm-budget true`
- critical `exit_code=9`: pass `--confirm-critical true`
- doctor path errors: check `.env` roots and rerun `bin/lacp-doctor --json`

## Optimization Backlog

Prioritized optimization findings are tracked in:
- `docs/optimization-audit-2026-02-20.md`
