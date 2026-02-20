# LACP Runbook

## First-Time Setup

```bash
cd ~/control/frameworks/lacp
bin/lacp-onboard
```

## Standard Verification Cycle

```bash
cd ~/control/frameworks/lacp
bin/lacp-verify --hours 24
```

Expected outputs:
- latest benchmark JSON path
- latest snapshot JSON path
- benchmark log path

## Health Diagnostics

```bash
cd ~/control/frameworks/lacp
bin/lacp-doctor
bin/lacp-doctor --json
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
