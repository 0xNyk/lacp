# LACP Runbook

## First-Time Setup

```bash
cd ~/control/frameworks/lacp
bin/lacp install --profile starter --with-verify
```

Alternative bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

## Standard Verification Cycle

```bash
cd ~/control/frameworks/lacp
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
bin/lacp skill-audit --json
bin/lacp migrate --json
bin/lacp status
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
