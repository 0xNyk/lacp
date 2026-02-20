# LACP

Local Agent Control Plane for Claude/Codex.

LACP turns local agent operations into an auditable system with:
- reproducible onboarding
- verification gates
- policy-based sandbox routing
- artifact-backed health and execution records

LACP is **not** a new runtime. It is a control plane around your existing local automation and agent tooling.

## End Goal

Make Claude/Codex operations:
- measurable (benchmarks, snapshots, diagnostics)
- reliable (verification loops, explicit pass/fail gates)
- safe (tiered execution with sandbox policy)
- reproducible (one-command setup and runbook workflows)

## Architecture

### Control-Plane Layer
- `bin/lacp-onboard`
- `bin/lacp-bootstrap`
- `bin/lacp-verify`
- `bin/lacp-doctor`

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

## Quick Start

```bash
cd ~/control/frameworks/lacp
cp config/lacp.env.example .env
bin/lacp-onboard
bin/lacp-doctor
bin/lacp-verify --hours 24
```

## Remote Setup

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
- `bin/lacp-bootstrap`: hard preflight (paths, scripts, policy file)
- `bin/lacp-verify`: memory pipeline + retrieval gates + snapshot + trend refresh
- `bin/lacp-doctor`: structured diagnostics (`--json` supported)
- `bin/lacp-route`: deterministic tier/provider routing with reasons
- `bin/lacp-sandbox-run`: route + dispatch + execution artifact logging
- `bin/lacp-remote-setup`: provider onboarding and config wiring
- `bin/lacp-remote-smoke`: provider-aware smoke test with artifact output

## Security Model

- No secrets in repo configuration files
- Environment-driven configuration in `.env`
- Policy-driven remote routing
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

## Optimization Backlog

Prioritized optimization findings are tracked in:
- `docs/optimization-audit-2026-02-20.md`
