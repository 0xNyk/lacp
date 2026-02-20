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

## Optimization Backlog

Prioritized optimization findings are tracked in:
- `docs/optimization-audit-2026-02-20.md`
