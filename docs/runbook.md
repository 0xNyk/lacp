# LACP Runbook

## First-Time Setup

```bash
cd ~/control/frameworks/lacp
bin/lacp bootstrap-system --profile starter --with-verify
```

Alternative bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

## Standard Verification Cycle

```bash
cd ~/control/frameworks/lacp
bin/lacp install --profile starter
bin/lacp install --profile starter --no-auto-deps
bin/lacp verify --hours 24
bin/lacp test --quick
bin/lacp test --isolated
```

Expected outputs:
- latest benchmark JSON path
- latest snapshot JSON path
- benchmark log path

## Health Diagnostics

```bash
cd ~/control/frameworks/lacp
bin/lacp doctor
bin/lacp doctor --json
bin/lacp doctor --fix
bin/lacp knowledge-doctor
bin/lacp knowledge-doctor --json
bin/lacp report --hours 24
bin/lacp cache-audit --hours 24 --json
bin/lacp cache-guard --hours 24 --min-hit-rate 0.70 --min-usage-events 100 --json
bin/lacp canary --json
bin/lacp canary-optimize --iterations 3 --hours 24 --json
bin/lacp canary --set-clean-baseline
bin/lacp canary --since-clean-baseline --json
bin/lacp vendor-watch --json
bin/lacp automations-tui --offline
bin/lacp automations-tui --json
bin/lacp auto-rollback --json
bin/lacp skill-audit --json
bin/lacp policy-pack list --json
bin/lacp policy-pack apply --pack starter --json
bin/lacp release-gate --quick
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --since-clean-baseline --json
bin/lacp open-source-check --skip-bootstrap --json
bin/lacp release-publish --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --skip-gh --json
bin/lacp pr-preflight --changed-files ./changed-files.txt --head-sha "$(git rev-parse HEAD)" --json
bin/lacp browser-evidence-validate --manifest ./browser-evidence.json --json
bin/lacp worktree doctor --repo-root . --json
bin/lacp orchestrate doctor --json
scripts/ci/test-harness-contracts.sh
bin/lacp harness-validate --tasks ./tasks.json --json
bin/lacp harness-run --tasks ./tasks.json --workdir . --json
bin/lacp harness-replay --run-id <run-id> --task-id <task-id> --workdir . --json
bin/lacp migrate --json
bin/lacp doctor --fix-deps --auto-deps-dry-run --json
bin/lacp schedule-health status --json
bin/lacp status
```

## Harness Contracts (Specs -> Tasks -> Loops)

Use these files as the source of truth for harness workflows:

- `config/harness/tasks.schema.json`
- `config/harness/sandbox-profiles.yaml`
- `config/harness/verification-policy.yaml`
- `config/harness/browser-evidence.schema.json`
- `config/risk-policy-contract.json`
- `config/risk-policy-contract.schema.json`

Validate locally:

```bash
cd ~/control/frameworks/lacp
./scripts/ci/test-harness-contracts.sh
```

## Pre-Live Go/No-Go Gate

```bash
cd ~/control/frameworks/lacp
bin/lacp release-gate
```

Default gate includes:
- full test suite
- `lacp-doctor`
- cache threshold gate (`min_hit_rate=0.70`, `min_usage_events=100`)
- skill supply-chain audit

Useful options:
- `--quick` to run quick tests instead of full suite
- `--cache-min-hit-rate <n>`
- `--cache-min-events <n>`
- `--skill-path <path>` (repeatable)
- `--json`

Recommended chained discipline:

```bash
cd ~/control/frameworks/lacp
bin/lacp canary --json | jq
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --since-clean-baseline --json | jq
```

## Optional Orchestrator Adapter (dmux/tmux/claude_worktree)

Use orchestration as an optional layer while keeping LACP as the gatekeeper:

```bash
cd ~/control/frameworks/lacp
bin/lacp orchestrate doctor --json | jq

# dmux (default backend, safe dry-run)
bin/lacp orchestrate run \
  --task "start dmux swarm" \
  --backend dmux \
  --session "lacp-dmux" \
  --command "codex --help" \
  --repo-trust trusted \
  --dry-run \
  --json | jq

# tmux (safe dry-run)
bin/lacp orchestrate run \
  --task "start swarm session" \
  --backend tmux \
  --session "lacp-swarm" \
  --command "claude --help" \
  --repo-trust trusted \
  --dry-run \
  --json | jq

# dmux live execution requires a template
export LACP_DMUX_RUN_TEMPLATE='dmux run --session "{session}" --command "{command}"'
bin/lacp orchestrate run \
  --task "start dmux swarm live" \
  --backend dmux \
  --session "lacp-dmux-live" \
  --command "codex --help" \
  --repo-trust trusted

# Claude native worktree isolation (safe dry-run)
bin/lacp orchestrate run \
  --task "start claude worktree stream" \
  --backend claude_worktree \
  --session "lacp-claude-batch-a" \
  --command "review open migration diffs and suggest fixes" \
  --repo-trust trusted \
  --claude-tmux true \
  --dry-run \
  --json | jq

# create/list/remove worktrees directly
bin/lacp worktree create --repo-root . --name "lacp-claude-batch-a" --base HEAD --json | jq
bin/lacp worktree list --repo-root . --json | jq
bin/lacp worktree gc --repo-root . --max-age-hours 72 --managed-only true --branch-prefix "wt/" --dry-run --json | jq
bin/lacp worktree remove --repo-root . --name "lacp-claude-batch-a" --force --json | jq

# batch orchestration
bin/lacp orchestrate run --batch ./orchestrate-batch.json --json | jq

# dmux-first swarm lifecycle
bin/lacp swarm init --manifest ./swarm.json --json | jq
bin/lacp swarm plan --manifest ./swarm.json --json | jq
bin/lacp swarm launch --manifest ./swarm.json --json | jq
bin/lacp swarm up --manifest ./swarm.json --json | jq
bin/lacp swarm tui --manifest ./swarm.json --dry-run --json | jq
bin/lacp swarm status --latest --json | jq

# adopt/revert local default claude/codex routing via LACP
bin/lacp adopt-local --json | jq
bin/lacp unadopt-local --json | jq
```

## Operating Mode

```bash
cd ~/control/frameworks/lacp
bin/lacp-mode show
bin/lacp-mode local-only
bin/lacp-mode remote-enabled --ttl-min 30
bin/lacp-mode revoke-approval
```

## Sandbox Routing

```bash
cd ~/control/frameworks/lacp

# Trusted local example
bin/lacp-route --task "run memory benchmark on internal repo" --repo-trust trusted

# Local sandbox example
bin/lacp-route \
  --task "run third-party scraper on unknown repo" \
  --repo-trust unknown \
  --internet true \
  --external-code true

# Remote sandbox example
bin/lacp-route \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true \
  --json
```

## Sandbox Execution Adapter

```bash
cd ~/control/frameworks/lacp

# Trusted local execution
bin/lacp-sandbox-run \
  --task "run internal benchmark checks" \
  --repo-trust trusted \
  -- echo "trusted-local-ok"

# Local sandbox route (falls back to direct if local runner unset)
bin/lacp-sandbox-run \
  --task "run third-party scraper on unknown repo" \
  --repo-trust unknown \
  --internet true \
  --external-code true \
  --input-contract '{"source":"operator","intent":"run scraper smoke","allowed_actions":["echo"],"denied_actions":["credential exfiltration"],"confidence":0.95}' \
  --confirm-critical true \
  -- echo "local-sandbox-ok"

# Remote route dry-run (safe when remote runner is not configured yet)
bin/lacp-sandbox-run \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true \
  --estimated-cost-usd 3.5 \
  --dry-run \
  --json
```

## Incident Drill

```bash
cd ~/control/frameworks/lacp
bin/lacp incident-drill --scenario retrieval-regression
bin/lacp incident-drill --scenario sandbox-gate-bypass --execute
```

## Deterministic Team Workflow

```bash
cd ~/control/frameworks/lacp
run_id="$(bin/lacp workflow-run init --task 'Add OAuth auth' --project auth --json | jq -r '.run_id')"
bin/lacp workflow-run advance --run-id "$run_id" --stage planner --actor planner
bin/lacp workflow-run advance --run-id "$run_id" --stage developer --actor developer
bin/lacp workflow-run advance --run-id "$run_id" --stage verifier --actor verifier --decision approve
bin/lacp workflow-run advance --run-id "$run_id" --stage tester --actor tester --decision approve
bin/lacp workflow-run advance --run-id "$run_id" --stage reviewer --actor reviewer --decision approve
bin/lacp workflow-run status --run-id "$run_id" --json | jq '.status,.current_stage'
```

## Zero-External Mode

Default recommended mode:

```bash
cd ~/control/frameworks/lacp
echo 'LACP_ALLOW_EXTERNAL_REMOTE="false"' >> .env
```

Behavior:
- routing still classifies remote tasks
- `--dry-run` remote checks still work
- live remote execution is blocked until explicitly enabled and approval TTL is valid
- risk tier `critical` always requires `--confirm-critical true`
- runs are blocked when `--estimated-cost-usd` exceeds tier budget unless `--confirm-budget true` is passed

## Daytona Runner (Remote Execution)

```bash
cd ~/control/frameworks/lacp
bin/lacp-remote-setup --provider daytona
daytona login
bin/lacp-remote-smoke --provider daytona --json
```

Run:

```bash
bin/lacp-sandbox-run \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true \
  -- python3 -V
```

## E2B Runner (Remote Execution)

Default integration mode uses non-interactive lifecycle (`create -> exec -> kill`) via E2B SDK.
Existing-sandbox mode remains available with `E2B_SANDBOX_ID`.

```bash
cd ~/control/frameworks/lacp

bin/lacp-remote-setup --provider e2b
export E2B_API_KEY="<your-api-key>"
bin/lacp-remote-smoke --provider e2b --json

bin/lacp-sandbox-run \
  --task "remote research batch" \
  --cpu-heavy true \
  --long-run true \
  -- python3 -V
```

Existing sandbox mode:

```bash
bin/lacp-remote-setup --provider e2b --e2b-sandbox-id "<running-e2b-sandbox-id>"
```

Preview only:

```bash
bin/lacp-remote-setup --provider daytona --dry-run --json
bin/lacp-remote-setup --provider e2b --dry-run --json
```

Remote smoke with custom command:

```bash
bin/lacp-remote-smoke --provider daytona -- python3 -V
```

## Troubleshooting

### Missing script errors

Confirm:
- `LACP_AUTOMATION_ROOT` points to your automation repo
- required scripts exist in `$LACP_AUTOMATION_ROOT/scripts`

### Missing benchmark artifacts

Confirm:
- benchmark script completed successfully
- output directory exists: `~/control/knowledge/knowledge-memory/data/benchmarks`

### Snapshot missing

Confirm:
- `capture_snapshot.py` exists
- output directory exists: `~/control/automation/ai-dev-optimization/data/snapshots`
