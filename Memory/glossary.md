# LACP Glossary

## intervention_rate_per_100
Definition: `(intervened_runs / total_runs) * 100`.
Meaning: Human intervention pressure normalized per 100 runs.

## intervened_runs
Runs classified as intervention-required by exit code policy (currently exit codes `8`, `9`, `10`).

## baseline window
A prior comparison window used to measure KPI drift. In report/status flows, selected via `--baseline-hours` and `--baseline-offset-hours`.

## delta (absolute)
`current_rate - baseline_rate` (in per-100-run units).

## delta (percent)
`(absolute_delta / baseline_rate) * 100`; `null` when baseline rate is zero.

## canary
Promotion-readiness gate over benchmark artifacts and quality thresholds.

## clean baseline
A recorded reference timestamp/artifact used to evaluate canary results only after a known-good point.

## local-first posture
Default operating mode that avoids external CI/remote execution unless explicitly enabled.

## context contract
Structured execution-context guard (host/cwd/git/worktree/remote target) used to prevent drift for risky commands.

## session fingerprint
Deterministic runtime identity signal used for anti-drift enforcement.

## harness
Task execution framework (`harness-validate/run/replay`) with contract checking and retry policies.

## swarm
Multi-session orchestration workflow with planning, launch, status, and collision analysis.

## artifacts
Structured outputs stored under automation/knowledge roots (runs, benchmarks, snapshots, reports).
