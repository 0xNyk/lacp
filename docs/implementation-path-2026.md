# LACP Implementation Path (Steps 1-6)

This document operationalizes the research-backed strategy:
- CLI/API-first execution
- minimal high-signal context
- harness/evidence as completion truth

## 1. Architecture Principle Lock

Target:
- Treat context as constraints, not narrative memory.
- Keep execution and verification in commands/artifacts.

Current implementation:
- `lacp` command surface remains CLI/API-first.
- `lacp up` + `orchestrate` + `swarm` support parallel execution without prompt bloat.

## 2. Context Layer (Template / Audit / Minimize / Regression)

Target:
- enforce minimal context files and A/B compare no-context vs minimal-context.

Current implementation:
- `lacp context init-template`
- `lacp context audit`
- `lacp context minimize`
- `lacp context regression --none <json> --minimal <json>`

## 3. Verification Default Completion Criterion

Target:
- no task marked done without machine-verifiable evidence.

Current implementation:
- Browser/API/contract evidence commands:
  - `lacp e2e ...`
  - `lacp api-e2e ...`
  - `lacp contract-e2e ...`
- `lacp pr-preflight` policy gating.
- `lacp test --isolated` full validation.

## 4. Parallel Execution Model

Target:
- standardized multi-instance flow with session isolation.

Current implementation:
- `lacp up` (dmux-style fanout)
- `lacp worktree` lifecycle
- `lacp swarm` reservation collision analysis
- context-contract + session fingerprint gates in sandbox run path

## 5. Self-Improvement Memory (No Bloat)

Target:
- one failure pattern -> one compact rule; dedupe and prune continuously.

Current implementation:
- `lacp lessons add-rule --rule "..."`
- `lacp lessons lint`

## 6. Weekly Optimization Loop

Target:
- close the loop with benchmarks + context/lessons health + concrete proposals.

Current implementation:
- `lacp optimize-loop --iterations 2 --hours 24 --days 7 --json`

---

## Suggested Weekly Runbook

```bash
bin/lacp context audit --repo-root . --json | jq
bin/lacp lessons lint --json | jq
bin/lacp optimize-loop --repo-root . --iterations 2 --hours 24 --days 7 --json | jq
bin/lacp release-prepare --profile local-iterative --json | jq
```
