# LACP Incident Response

## Scope

This runbook covers local control-plane incidents for:
- retrieval regressions (benchmark gate failures, dense index drift)
- sandbox control regressions (approval/budget/risk-tier bypass)
- memory sync drift (stale or broken context ingestion)

## Severity

- `SEV1`: gate bypass or corrupted run artifacts affecting trust.
- `SEV2`: benchmark gate failures or dense retrieval unavailable.
- `SEV3`: sync drift, stale docs, or degraded but safe behavior.

## Response Flow

1. Detect and classify severity.
2. Contain (set `bin/lacp mode local-only` for remote-risk incidents).
3. Collect evidence:
   - `bin/lacp doctor --json`
   - `bin/lacp status --json`
   - latest benchmark + triage files in `data/benchmarks/`
4. Recover:
   - rerun `bin/lacp verify --hours 24`
   - rerun relevant CI tests (`test-mode-and-gates.sh`, `smoke.sh`)
5. Confirm recovery with gates and doctor.
6. Record lessons in `memory/lessons.md` and update controls.

## Drill Command

Use scenario drills to validate readiness:

```bash
bin/lacp incident-drill --scenario retrieval-regression
bin/lacp incident-drill --scenario retrieval-regression --execute
bin/lacp incident-drill --scenario sandbox-gate-bypass --execute
bin/lacp incident-drill --scenario memory-sync-drift --execute
```

Artifacts are written to:
- `$LACP_KNOWLEDGE_ROOT/data/incidents/drills/*.json`
- `$LACP_KNOWLEDGE_ROOT/data/incidents/drills/*.md`
