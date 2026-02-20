# LACP

Local Agent Control Plane for Claude/Codex operations.

`LACP` is a control-plane wrapper around local automation you already run:
- shared memory extraction + sync
- hybrid retrieval benchmark + gates
- snapshot capture for latency/health tracking

It does not replace agent runtimes. It standardizes operations, evidence, and reproducible onboarding.

## Scope

- Memory + knowledge pipeline orchestration
- Retrieval gate verification and evidence collection
- Local bootstrap checks for required roots/scripts
- Runbook-first operations for repeatability

## Quick Start

```bash
cd ~/control/frameworks/lacp
cp config/lacp.env.example .env
bin/lacp-onboard
bin/lacp-verify --hours 24
bin/lacp-doctor
bin/lacp-route --task "run quant backtest with gpu" --cpu-heavy true --long-run true --json
bin/lacp-sandbox-run --task "run internal checks" --repo-trust trusted -- echo "ok"
bin/lacp-remote-setup --provider daytona
```

## Defaults

These defaults are used unless overridden by env vars in `.env` or shell:

- `LACP_AUTOMATION_ROOT=$HOME/control/automation/ai-dev-optimization`
- `LACP_KNOWLEDGE_ROOT=$HOME/control/knowledge/knowledge-memory`
- `LACP_DRAFTS_ROOT=$HOME/docs/content/drafts`

## Commands

- `bin/lacp-onboard`
  - creates `.env` from template if missing
  - runs bootstrap checks
  - optional full verification: `bin/lacp-onboard --with-verify`
- `bin/lacp-bootstrap`
  - validates command dependencies
  - validates expected directory roots
  - validates required automation scripts exist
- `bin/lacp-verify`
  - runs shared memory extraction and sync
  - runs retrieval benchmark suite with gates
  - captures a fresh system snapshot
  - prints latest benchmark and snapshot artifacts
- `bin/lacp-doctor`
  - validates required commands/paths/scripts
  - checks Ollama endpoint reachability
  - inspects latest benchmark/snapshot artifacts
  - machine-readable output: `bin/lacp-doctor --json`
- `bin/lacp-route`
  - applies sandbox routing policy (`trusted_local | local_sandbox | remote_sandbox`)
  - resolves remote provider (`daytona | e2b`) for remote routes
  - returns explainable routing reasons
  - machine-readable output: `bin/lacp-route --task "<...>" --json`
- `bin/lacp-sandbox-run`
  - runs command via policy-selected execution tier
  - writes run artifacts to `~/control/knowledge/knowledge-memory/data/sandbox-runs/*.json`
  - local sandbox can use optional runner; remote sandbox requires explicit runner config
- `bin/lacp-remote-setup`
  - one-command provider setup for remote execution lane (`daytona` or `e2b`)
  - can update policy + `.env` and report auth/next steps
  - dry-run mode: `bin/lacp-remote-setup --provider daytona --dry-run --json`

## Daytona Remote Runner Setup

```bash
cd ~/control/frameworks/lacp
daytona login

# add to .env
LACP_REMOTE_SANDBOX_RUNNER="$HOME/control/frameworks/lacp/scripts/runners/daytona-runner.sh"
```

Example:

```bash
bin/lacp-sandbox-run \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true \
  -- python3 -V
```

## E2B Remote Runner Setup

```bash
cd ~/control/frameworks/lacp

# set policy provider if desired
# (edit config/sandbox-policy.json -> routing.remote_provider = "e2b")

# optional explicit override:
LACP_REMOTE_SANDBOX_RUNNER="$HOME/control/frameworks/lacp/scripts/runners/e2b-runner.sh"
E2B_SANDBOX_ID="<running-sandbox-id>"
```

## Artifact Paths

- Benchmark reports: `~/control/knowledge/knowledge-memory/data/benchmarks/*.json`
- Snapshot reports: `~/control/automation/ai-dev-optimization/data/snapshots/*.json`
- Benchmark log: `~/control/knowledge/knowledge-memory/data/benchmark.log`

## Documentation

- `docs/runbook.md`
- `docs/framework-scope.md`
