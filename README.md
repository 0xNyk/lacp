# LACP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.1.x-blue)]()

![LACP Banner](docs/assets/readme-banner.png)

**Local Agent Control Plane** — production-grade guardrails for Claude and Codex on your machine.

LACP wraps your existing local agent tooling with auditable execution gates, policy-based sandbox routing, and artifact-backed health records. No new runtime — just a control plane that makes local AI operations measurable, reliable, and safe.

## What LACP Does

- **Execution gates** — risk-tier routing (`safe` / `review` / `critical`) with TTL approvals, budget ceilings, and context contracts
- **Sandbox routing** — deterministic policy engine routes tasks to `trusted_local`, `local_sandbox`, or `remote_sandbox` (Daytona / E2B)
- **Multi-agent isolation** — dmux-style parallel sessions, git worktree lifecycle, and swarm orchestration in one command
- **Evidence pipelines** — browser e2e, API e2e, and smart-contract e2e harnesses that generate machine-verifiable artifacts
- **Knowledge brain** — Obsidian vault integration with automated research sync, brain expansion loops, and skill management
- **Release discipline** — canary promotion gates, release verification, open-source readiness checks, and vendor drift monitoring

---

## Table of Contents

- [Quick Start](#quick-start)
- [Daily Workflow](#daily-workflow)
- [Architecture](#architecture)
- [Execution Model](#execution-model)
- [Install Options](#install-options)
- [Command Reference](#command-reference)
- [Configuration & Contracts](#configuration--contracts)
- [Security Model](#security-model)
- [Obsidian Brain Bundle](#obsidian-brain-bundle)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Quick Start

```bash
# Install and verify in one shot
brew tap 0xNyk/lacp && brew install --HEAD lacp

# Or bootstrap from source
git clone https://github.com/0xNyk/lacp.git && cd lacp
bin/lacp bootstrap-system --profile starter --with-verify

# Verify everything works
bin/lacp doctor --json | jq '.ok'
bin/lacp test --quick
bin/lacp status --json | jq
```

Prerequisites: `bash`, `python3`, `jq`, `rg` (ripgrep). Optional: `shellcheck`.

---

## Daily Workflow

### 1. Health check

```bash
bin/lacp doctor --fix-hints
bin/lacp system-health --fix-hints
```

### 2. Set operating mode

```bash
bin/lacp mode local-only                      # default safe mode
bin/lacp mode remote-enabled --ttl-min 30     # temporary remote access
```

### 3. Run work through gates

```bash
bin/lacp run --task "trusted smoke" --repo-trust trusted -- /bin/echo hello
bin/lacp loop --task "implement feature X" --repo-trust trusted --json -- <command>
```

### 4. Parallel agent isolation

```bash
bin/lacp up --session dev --instances 3 --command "claude" --json | jq
bin/lacp worktree create --repo-root . --name "feature-a" --base HEAD --json | jq
bin/lacp swarm launch --manifest ./swarm.json --json | jq
```

### 5. Generate evidence

```bash
bin/lacp e2e smoke --workdir . --init-template --command "npx playwright test --grep @smoke" --json | jq
bin/lacp api-e2e smoke --workdir . --init-template --command "npx schemathesis run --checks all" --json | jq
bin/lacp pr-preflight --changed-files ./changed-files.txt --checks-json ./checks.json --review-json ./review-state.json --json | jq
```

### 6. Release

```bash
bin/lacp release-prepare --profile local-iterative --json | jq
bin/lacp release-verify --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
```

### 7. Optional — route `claude`/`codex` through LACP by default

```bash
bin/lacp adopt-local --force --json | jq
```

---

## Architecture

LACP is organized in four layers:

| Layer | Purpose | Key files |
|-------|---------|-----------|
| **Control Plane** | Install, onboard, verify, diagnose | `bin/lacp-install`, `bin/lacp-onboard`, `bin/lacp-doctor`, `bin/lacp-verify` |
| **Policy + Routing** | Sandbox policy, route decisions, execution dispatch | `config/sandbox-policy.json`, `bin/lacp-route`, `bin/lacp-sandbox-run` |
| **Harness Contract** | Task schemas, sandbox profiles, verification policies | `config/harness/tasks.schema.json`, `config/harness/sandbox-profiles.yaml` |
| **Remote Provider** | Daytona and E2B runner adapters | `bin/lacp-remote-setup`, `scripts/runners/daytona-runner.sh` |

---

## Execution Model

### Execution Tiers

| Tier | When used |
|------|-----------|
| `trusted_local` | Known low-risk tasks |
| `local_sandbox` | Semi-trusted work requiring isolation |
| `remote_sandbox` | High-risk, high-compute, or long-running tasks |

Remote provider (`daytona` or `e2b`) is policy-driven with override support.

### Risk Tiers

| Risk | Behavior |
|------|----------|
| `safe` | Executes without approval gate |
| `review` | Requires valid TTL approval token (`bin/lacp mode remote-enabled --ttl-min <N>`) |
| `critical` | Always requires explicit per-run confirmation (`--confirm-critical true`) |

### Budget Gates

Per-tier cost ceilings are set in `config/sandbox-policy.json` under `routing.cost_ceiling_usd_by_risk_tier`. Pass `--estimated-cost-usd <N>` to `bin/lacp-sandbox-run`. Exceeding the ceiling blocks the run unless `--confirm-budget true` is provided.

### Context Contracts

Mutating and remote-target commands require a context contract by default. Pass `--context-contract '<json>'` with expectations like `expected_host`, `expected_cwd_prefix`, `expected_git_branch`, `expected_remote_host`.

```bash
bin/lacp-sandbox-run \
  --task "create local venv" \
  --repo-trust trusted \
  --context-contract '{"expected_host":"my-host","expected_cwd_prefix":"'"$HOME"'/control"}' \
  -- python3 -m venv .venv
```

---

## Install Options

### Homebrew (recommended)

```bash
brew tap 0xNyk/lacp
brew install --HEAD lacp
```

### cURL bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

Optional flags: `--ref main`, `--profile starter`, `--with-verify true`.

### Verified release (production)

```bash
VERSION="0.1.0"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/lacp-${VERSION}.tar.gz"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/SHA256SUMS"
grep "lacp-${VERSION}.tar.gz" SHA256SUMS | shasum -a 256 -c -
tar -xzf "lacp-${VERSION}.tar.gz" && cd "lacp-${VERSION}"
bin/lacp-install --profile starter --with-verify
```

The installer creates `.env` from template, auto-detects missing macOS dependencies (`jq`, `ripgrep`, `python@3.11`, `tmux`, `gh`, `node`, Obsidian), bootstraps the Obsidian vault, applies starter policy defaults, and runs verification. Use `--no-auto-deps` or `--no-obsidian-setup` to skip.

---

## Command Reference

### Core

| Command | Description |
|---------|-------------|
| `lacp bootstrap-system` | One-command install + onboard + doctor flow |
| `lacp install` | First-time installer with auto-deps and vault bootstrap |
| `lacp onboard` | Initialize `.env`, run bootstrap, optimize Claude hooks/profile |
| `lacp doctor` | Structured diagnostics (`--json`, `--check-limits`, `--fix-hints`, `--system`) |
| `lacp system-health` | macOS/Apple Silicon readiness (thermal, memory, Spotlight, Docker, Rust, UI) |
| `lacp verify` | Memory pipeline + retrieval gates + snapshot + trend refresh |
| `lacp status` | Compact system snapshot |
| `lacp mode` | Switch operating mode (`local-only` / `remote-enabled` / `revoke-approval`) |
| `lacp posture` | Local-first / no-external-CI contract report (`--strict`, `--json`) |
| `lacp test` | Local test suite (`--quick`, `--isolated`) |

### Execution & Loops

| Command | Description |
|---------|-------------|
| `lacp run` | Single command with routing / risk / budget / context gates |
| `lacp loop` | One-task control loop: intent → execute → observe → adapt |
| `lacp loop-profile` | List/render reusable loop defaults (routing + verify posture) |
| `lacp context-profile` | List/render reusable context-contract profiles |
| `lacp credential-profile` | List/render credential posture and input-contract templates |
| `lacp session-fingerprint` | Derive deterministic session fingerprint for anti-drift gates |
| `lacp route` | Deterministic tier/provider routing with reasons |
| `lacp sandbox-run` | Route + risk/budget gates + dispatch + artifact logging |

### Isolation & Orchestration

| Command | Description |
|---------|-------------|
| `lacp up` | dmux-style multi-instance launch (`--layout`, `--brand`, `--instances`) |
| `lacp orchestrate` | dmux/tmux/claude_worktree orchestration adapter |
| `lacp worktree` | Git worktree lifecycle (`list/create/remove/prune/gc/doctor`) |
| `lacp swarm` | dmux-first swarm workflow (`init/plan/launch/up/tui/status`) |
| `lacp adopt-local` | Install reversible `claude`/`codex` wrappers routing through LACP |
| `lacp unadopt-local` | Remove LACP wrappers, restore previous shims |
| `lacp console` | Interactive slash-command shell (`/doctor`, `/up`, `/loop`, `/release`, etc.) |
| `lacp workflow-run` | Planner → developer → verifier → tester → reviewer workflow skeleton |

### Evidence & E2E

| Command | Description |
|---------|-------------|
| `lacp e2e` | Playwright-style e2e + evidence manifest + auth pattern checks |
| `lacp api-e2e` | API/backend e2e wrappers with manifest evidence + coverage checks |
| `lacp contract-e2e` | Smart-contract e2e wrappers with invariant/revert checks |
| `lacp browser-evidence-validate` | Validate browser evidence manifests with freshness/assertion gates |
| `lacp pr-preflight` | PR policy gates (risk tier + docs drift + check runs + review state) |
| `lacp harness-validate` | Validate `tasks.json` against schema + profile/policy catalogs |
| `lacp harness-run` | Execute validated tasks with dependency ordering + loop retries |
| `lacp harness-replay` | Replay failed tasks with failure classification + remediation hints |

### Release & Quality

| Command | Description |
|---------|-------------|
| `lacp release-prepare` | Pre-live discipline (release-gate + canary + status + report) |
| `lacp release-publish` | Local-only artifact builder/publisher (`tar.gz` + `SHA256SUMS` + optional `gh release`) |
| `lacp release-verify` | Release verification (checksum + archive + brew dry-run) |
| `lacp release-gate` | Strict pre-live go/no-go checks (tests + doctor + cache + skills) |
| `lacp open-source-check` | Open-source readiness gate (docs, security, deps, checksums) |
| `lacp canary` | 7-day promotion gate over retrieval benchmarks |
| `lacp canary-optimize` | Bounded optimization loop (verify → canary) |
| `lacp auto-rollback` | Fail-safe rollback on unhealthy canary |
| `lacp vendor-watch` | Monitor Claude/Codex version and upstream drift |

### Knowledge & Brain

| Command | Description |
|---------|-------------|
| `lacp brain-doctor` | Obsidian brain ecosystem checks (vault, QMD, MCP, freshness) |
| `lacp brain-expand` | Automated brain expansion loop (session sync, research, consolidation) |
| `lacp repo-research-sync` | Mirror repo research docs into Obsidian graph |
| `lacp skill-sync-anthropic` | Sync official Anthropic skills to local skill paths |
| `lacp knowledge-doctor` | Markdown knowledge graph quality gates |
| `lacp skill-factory` | Operate auto-skill-factory (summary/capture/record/lifecycle) |
| `lacp skill-audit` | Detect risky skill patterns before install/use |
| `lacp lessons` | Add/lint compact self-improvement rules |

### System & Ops

| Command | Description |
|---------|-------------|
| `lacp claude-hooks` | Audit/repair/optimize Claude hook/plugin drift |
| `lacp context` | Context lifecycle (`init-template`, `audit`, `minimize`, `regression`) |
| `lacp optimize-loop` | Bounded weekly optimization loop |
| `lacp trace-triage` | Cluster failed run traces into root-cause groups |
| `lacp policy-pack` | List/apply policy baseline packs (`starter`, `strict`, `enterprise`) |
| `lacp schedule-health` | Install/manage scheduled local health checks via launchd |
| `lacp cache-audit` | Measure prompt cache efficiency from local histories |
| `lacp cache-guard` | Enforce cache health thresholds |
| `lacp time` | Monthly project/client session time tracking with tag/activity rollups |
| `lacp report` | Summarize recent run outcomes and artifact health |
| `lacp migrate` | Migrate existing local roots into `.env` (dry-run by default) |
| `lacp incident-drill` | Run scenario-based incident readiness drills |
| `lacp automations-tui` | Unified local automation dashboard |
| `lacp mcp-profile` | List/status/apply MCP operating profiles |
| `lacp remote-setup` | Provider onboarding and config wiring |
| `lacp remote-smoke` | Provider-aware smoke test with artifact output |

---

## Configuration & Contracts

| File | Purpose |
|------|---------|
| `config/sandbox-policy.json` | Sandbox routing policy and cost ceilings |
| `config/risk-policy-contract.json` | Risk/merge/review/evidence policy contract |
| `config/risk-policy-contract.schema.json` | Schema for drift-resistant validation |
| `config/harness/tasks.schema.json` | Task plan contract (supports cascading IO contracts) |
| `config/harness/sandbox-profiles.yaml` | Reproducible sandbox/runtime presets |
| `config/harness/verification-policy.yaml` | Per-task verification requirements and failure actions |
| `config/harness/browser-evidence.schema.json` | Browser flow evidence contract |

The harness system maps: **spec → orchestrator-generated tasks → sandbox profile + verification policy → checkable gate outcomes**.

Validate and run a task plan:

```bash
bin/lacp harness-validate --tasks ./tasks.json --json | jq
bin/lacp harness-run --tasks ./tasks.json --workdir . --json | jq
```

---

## Security Model

- **No secrets in repo** — environment-driven configuration via `.env`
- **Zero-external-cost by default** — local CLI gates, no required GitHub Actions or paid CI
- **Remote execution disabled by default** — `LACP_ALLOW_EXTERNAL_REMOTE=false`
- **Risk-tier gating** — `safe`/`review`/`critical` with TTL and per-run confirmation
- **Context contracts** — structured input validation for mutating/remote commands
- **Artifact audit trail** — structured logs for every sandbox run
- **Cache observability** — prompt cache efficiency from provider-native history schemas

See also: [`SECURITY.md`](SECURITY.md), [`docs/framework-scope.md`](docs/framework-scope.md), [`docs/incident-response.md`](docs/incident-response.md), [`docs/runbook.md`](docs/runbook.md).

---

## Obsidian Brain Bundle

LACP includes first-class Obsidian integration:

- **Vault bootstrap** at `$LACP_OBSIDIAN_VAULT` (default: `~/obsidian/vault`) during install
- **QMD indexing** via `@tobilu/qmd` installed by default
- **Brain health**: `bin/lacp brain-doctor --json | jq`
- **Brain expansion**: `bin/lacp brain-expand --apply --json | jq`
- **Repo research sync**: `bin/lacp repo-research-sync --apply --json | jq`
- **Anthropic skill sync**: `bin/lacp skill-sync-anthropic --skill skill-creator --apply --json | jq`

Recommended automation (launchd): repo research sync every 30 min, full brain-expand every 6 hours. See `docs/` for launchd plist examples.

---

## Remote Setup

LACP runs in **zero-external mode** by default. Remote execution requires explicit opt-in:

```bash
# Enable remote mode with TTL
bin/lacp mode remote-enabled --ttl-min 30

# Daytona
bin/lacp remote-setup --provider daytona
bin/lacp remote-smoke --provider daytona --json

# E2B
bin/lacp remote-setup --provider e2b --e2b-sandbox-id "<sandbox-id>"
bin/lacp remote-smoke --provider e2b --json
```

---

## Testing

```bash
bin/lacp test              # full test suite
bin/lacp test --quick      # fast smoke tests
bin/lacp test --isolated   # isolated environment tests
```

Individual test scripts live in `scripts/ci/`:

```bash
scripts/ci/smoke.sh
scripts/ci/test-route-policy.sh
scripts/ci/test-mode-and-gates.sh
scripts/ci/test-knowledge-doctor.sh
scripts/ci/test-ops-commands.sh
scripts/ci/test-install.sh
scripts/ci/test-system-health.sh
```

---

## Artifacts

| Type | Location |
|------|----------|
| Benchmark reports | `$LACP_KNOWLEDGE_ROOT/data/benchmarks/*.json` |
| Snapshots | `$LACP_AUTOMATION_ROOT/data/snapshots/*.json` |
| Sandbox runs | `$LACP_KNOWLEDGE_ROOT/data/sandbox-runs/*.json` |
| Remote smoke runs | `$LACP_KNOWLEDGE_ROOT/data/remote-smoke/*.json` |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `bootstrap failed missing script` | `bin/lacp install --profile starter --force-scaffold` |
| `fork: Resource temporarily unavailable` | `bin/lacp doctor --check-limits --fix-hints` — reduce concurrent sessions or raise `ulimit -u` |
| Remote `exit_code=8` | `bin/lacp mode remote-enabled --ttl-min 30` |
| Budget `exit_code=10` | Lower `--estimated-cost-usd` or pass `--confirm-budget true` |
| Critical `exit_code=9` | Pass `--confirm-critical true` |
| Doctor path errors | Check `.env` roots, rerun `bin/lacp doctor --json` |

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development guidelines and [`SECURITY.md`](SECURITY.md) for reporting vulnerabilities.

## License

[MIT](LICENSE)
