# Heartbeat

Last updated: 2026-03-12 (UTC)
Phase: 6 - Memory System

## What we built (executive summary)

LACP is now a local-first agent control plane with strong guardrails, observable operations, and growing memory/knowledge workflows.

### Control plane and safety
- Top-level `lacp` dispatcher with composable subcommands.
- Policy/routing engine (`trusted_local`, `local_sandbox`, `remote_sandbox`) with risk tiers (`safe`, `review`, `critical`).
- Approval + budget gates, input contracts, context contracts, and session fingerprint controls.
- Local wrapper adopt/unadopt flow for `claude` / `codex` through LACP gates.

### Verification and operational discipline
- Health surfaces: `doctor`, `status`, `report`, `system-health`, `mcp-health`, `knowledge-doctor`, `brain-doctor`.
- Promotion discipline: `canary`, clean baseline controls, release gate/prepare/verify/publish.
- Fail-safe response: `auto-rollback` and scheduled health automation.
- Rich observability artifacts under automation/knowledge roots.

### Runtime workflows
- Loop/optimization workflows (`loop`, `optimize-loop`, `trace-triage`).
- Orchestration/worktrees/swarm workflows with deterministic contracts.
- Harness engine (`harness-validate`, `harness-run`, `harness-replay`) with task contracts and retries.
- Browser/API/contract e2e workflows with evidence validation.

### Knowledge + memory stack
- `brain-ingest`, `brain-stack`, `brain-expand`, and repo research sync.
- Obsidian-oriented memory operations and knowledge-graph hygiene tooling.
- Time tracking and operational reporting integrated into daily workflows.

### CI/test posture
- Broad shell-based CI coverage across ops, routing, canary/baseline, releases, harness, swarm, and knowledge paths.
- Local-first/no-external-ci posture enforced by policy and tests.

## Recent milestone notes
- Added first-class intervention pressure KPI:
  - `intervention_rate_per_100 = (intervened_runs / total_runs) * 100`
  - baseline window compare with absolute + percent delta
  - surfaced in `lacp-report` and now in `lacp-status-report` JSON + human-readable output
  - covered by CI assertions (`test-report-intervention-rate.sh`, `test-ops-commands.sh`)

## Current focus
- Consolidate phase-based operational memory in this `Memory/` tree.
- Keep definitions and handoff context stable across sessions.
- Make operator status/report/canary signals easy to compare over time.

## Next actions
1. Keep this file updated when major capabilities land.
2. Record durable people/project/context notes in `Memory/`.
3. Expand glossary whenever new commands/terms become operator-critical.
