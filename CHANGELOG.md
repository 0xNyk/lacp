# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- `bin/lacp-bootstrap-system` one-command first-run bootstrap (`install + onboard + doctor`).
- `bin/lacp-canary` for 7-day promotion readiness gates over benchmark artifacts.
- `bin/lacp-canary-optimize` bounded optimization loop with optional `LACP_BENCH_TOP_K` auto-tuning and persistence.
- `bin/lacp-vendor-watch` to track local Claude/Codex versions and upstream docs/changelog drift snapshots.
- `bin/lacp-automations-tui` unified local automation dashboard for schedule/orchestrate/worktree/swarm/wrapper/vendor state.
- `lacp-canary` clean baseline controls: `--set-clean-baseline`, `--since-clean-baseline`.
- `bin/lacp-auto-rollback` fail-safe rollback command (forces `local-only` + unadopts local wrappers) on unhealthy canary.
- `bin/lacp-schedule-health` launchd automation for periodic local health artifacts (`doctor/status/report`).
- `bin/lacp-policy-pack` with baseline packs:
  - `config/policy-packs/starter.json`
  - `config/policy-packs/strict.json`
  - `config/policy-packs/enterprise.json`
- `bin/lacp-release-prepare` one-command release discipline (`release-gate` + `canary` + `status` + `report`) with optional rollback trigger.
- `bin/lacp-loop` one-task control loop (`intent -> execute -> observe -> adapt`) with optional verify/canary/auto-rollback stages.
- `bin/lacp-trace-triage` deterministic clustering of failed sandbox traces (`context_drift`/`policy_block`/`env_missing`/`test_fail`) with ranked signatures and remediation recommendations.
- `bin/lacp-sandbox-run --context-contract` with mutating-run context enforcement (`host/cwd/git branch/worktree`) and structured evidence in run artifacts.
- `bin/lacp-sandbox-run` context-contract gate now covers remote-target commands (`ssh`/`scp`/`rsync`/`sftp`) with `expected_remote_host` validation.
- CI coverage for new surfaces:
  - `scripts/ci/test-bootstrap-system.sh`
  - `scripts/ci/test-canary-optimize.sh`
  - `scripts/ci/test-vendor-watch.sh`
  - `scripts/ci/test-automations-tui.sh`
  - `scripts/ci/test-auto-deps.sh`
  - `scripts/ci/test-canary.sh`
  - `scripts/ci/test-canary-baseline.sh`
  - `scripts/ci/test-auto-rollback.sh`
  - `scripts/ci/test-schedule-health.sh`
  - `scripts/ci/test-policy-pack.sh`
  - `scripts/ci/test-release-prepare.sh`
  - `scripts/ci/test-loop.sh`
  - `scripts/ci/test-trace-triage.sh`

### Changed
- `bin/lacp-install` now enables fresh-system dependency auto-detection by default on macOS/Homebrew (`--no-auto-deps` opt-out, `--auto-deps-dry-run` supported).
- `bin/lacp-onboard` now performs default dependency auto-detection/remediation on macOS/Homebrew (`--no-auto-deps` opt-out).
- `bin/lacp-canary-optimize --json` now keeps JSON parse-safe output even in `--dry-run` mode.
- `bin/lacp-release-prepare` now supports baseline-aware canary evaluation (`--since-clean-baseline`, `--baseline-file`).
- `bin/lacp-doctor` now supports dependency remediation mode (`--fix-deps`, `--auto-deps-dry-run`).
- `bin/lacp-report` now includes wrapper observability (`observability.wrappers`, wrapper-routed runs, wrapper-task runs).
- `bin/lacp-status-report` and `bin/lacp-report` JSON outputs now share top-level schema fields (`schema_version`, `kind`, `ok`, `summary`).
- `bin/lacp` top-level dispatcher expanded with new commands (`canary`, `auto-rollback`, `schedule-health`, `policy-pack`, `release-prepare`).
- `bin/lacp` top-level dispatcher expanded with `canary-optimize`.
- `bin/lacp` top-level dispatcher expanded with `loop`.
- `bin/lacp-loop --json` now emits deterministic failure analysis (`analysis.primary_cause`, `analysis.secondary_causes`, `analysis.signals`, `analysis.remediation_hints`, `analysis.confidence`) for faster post-run triage.
- `bin/lacp-workflow-run advance` now enforces explicit `plan->act` handoff: planner issues token, developer must present matching `--plan-token` (or explicit `--allow-unplanned true` bypass).
- Homebrew formula command export list updated for new binaries.
- Security controls CI now covers context-contract gate behavior (`missing`, `mismatch`, `pass`) for mutating commands.

## [0.1.0] - 2026-02-20

### Added
- `bin/lacp` top-level CLI dispatcher (`start/install/doctor/test/...`).
- `bin/lacp-incident-drill` for scenario-based incident readiness checks with artifacts.
- `bin/lacp-cache-audit` to track prompt cache effectiveness from local Claude/Codex history logs.
- Cache audit upgraded to parse provider-native schemas (`.codex/sessions` token_count and `.claude/projects` assistant usage).
- `bin/lacp-cache-guard` to enforce minimum cache hit-rate and usage-event thresholds.
- `bin/lacp-skill-audit` to detect high-risk skill supply-chain patterns (`curl|bash`, reverse shell signatures, etc.).
- `bin/lacp-release-gate` for one-command pre-live go/no-go checks across tests, doctor, cache, and skill audit.
- `config/risk-policy-contract.json` + `config/risk-policy-contract.schema.json` for one-source PR gate policy contract.
- `bin/lacp-pr-preflight` to enforce risk-tier required checks, docs drift rules, current-head review state, and browser evidence gates.
- `config/harness/browser-evidence.schema.json` + `bin/lacp-browser-evidence-validate` for machine-verifiable UI/user-flow evidence.
- `bin/lacp-orchestrate` optional tmux/dmux adapter (`doctor`, `run`) routed through existing LACP sandbox gates.
- `lacp-orchestrate` now supports `claude_worktree` backend with optional `--claude-tmux` wiring into Claude native worktree isolation.
- `scripts/runners/claude-worktree-runner.sh` for policy-gated Claude `--worktree` dispatch.
- `bin/lacp-worktree` for explicit git worktree lifecycle management (`list/create/remove/prune/doctor`).
- `bin/lacp-worktree gc` retention mode (`--max-age-hours`, `--managed-only`, `--branch-prefix`) for stale worktree cleanup.
- `lacp-orchestrate run --batch <manifest>` for multi-session launches with deterministic stop/continue-on-error behavior.
- `lacp-orchestrate` default backend switched to `dmux` (override with `LACP_ORCHESTRATOR_BACKEND` or `--backend`).
- `bin/lacp-swarm` dmux-first swarm lifecycle (`init`, `plan`, `launch`, `up`, `tui`, `status`) with artifacted launches under `knowledge/data/swarms`.
- `bin/lacp-adopt-local` and `bin/lacp-unadopt-local` for reversible local default routing of `claude`/`codex` through LACP policy gates.
- Harness contract layer:
  - `config/harness/tasks.schema.json`
  - `config/harness/sandbox-profiles.yaml`
  - `config/harness/verification-policy.yaml`
- Harness contracts validation test: `scripts/ci/test-harness-contracts.sh`.
- `bin/lacp-harness-validate` for tasks plan validation + profile/policy cross-checks.
- `bin/lacp-harness-run` for dependency-aware task execution with loop retries and attempt artifacts.
- Harness validate CI coverage: `scripts/ci/test-harness-validate.sh`.
- Harness run CI coverage: `scripts/ci/test-harness-run.sh`.
- Browser evidence CI coverage: `scripts/ci/test-browser-evidence-validate.sh`.
- PR preflight CI coverage: `scripts/ci/test-pr-preflight.sh`.
- Orchestrate CI expanded with `claude_worktree` backend coverage.
- Worktree command CI coverage: `scripts/ci/test-worktree.sh`.
- Orchestrate CI expanded with batch-manifest execution coverage.
- Swarm command CI coverage: `scripts/ci/test-swarm.sh`.
- Local wrapper adopt/unadopt CI coverage: `scripts/ci/test-adopt-local.sh`.
- Workflow cost-policy gate: `scripts/ci/test-workflow-cost-policy.sh` enforcing official actions-only and blocking paid-provider workflow hooks.
- `bin/lacp-workflow-run` deterministic multi-role workflow skeleton (`planner -> developer -> verifier -> tester -> reviewer`).
- MCP auth policy file (`config/mcp-auth-policy.json`) and doctor policy validation checks.
- Release workflow (`.github/workflows/release.yml`) generating versioned tarball + `SHA256SUMS`.
- `bin/lacp-report` for recent execution and artifact summaries.
- `bin/lacp-migrate` for existing-stack `.env` migration (dry-run/apply).
- `bin/lacp-doctor --fix` safe remediations for common setup drift.
- Ops command CI coverage via `scripts/ci/test-ops-commands.sh`.
- Homebrew formula (`Formula/lacp.rb`) for tap-based installs.
- cURL installer (`install.sh`) with ref/profile/verify options.
- `bin/lacp-test` one-command validation runner.
- `bin/lacp-test --isolated` for temporary-root safety when testing on active local setups.
- `bin/lacp-install` first-time installer with `starter` scaffolding profile.
- Install workflow CI coverage via `scripts/ci/test-install.sh`.
- Local agent control-plane baseline with onboarding, verify, doctor, mode, and status reporting commands.
- Policy-based route engine with tiered execution (`trusted_local`, `local_sandbox`, `remote_sandbox`).
- Remote runner support for Daytona and E2B with setup and smoke commands.
- Zero-external default mode and explicit remote enablement controls.
- Review/critical risk-gate model:
  - `safe`: no approval gate
  - `review`: TTL approval required
  - `critical`: explicit per-run confirmation required
- Per-tier budget ceilings and budget override confirmation gate.
- Structured run artifacts for route decision, risk tier, approvals, and provider metadata.
- CI suite including syntax checks, shellcheck, route-policy tests, mode-and-gate unit tests, and smoke tests.

### Security
- Default-deny posture for remote execution.
- Approval TTL and explicit confirmation gates for higher-risk operations.
- `lacp-test --isolated` now enforces `.env` integrity and fails on mutation.
- Structured input-contract gate for risky sandbox runs (`--input-contract`, exit code `11` on violation).
- Release workflow no longer depends on third-party actions; uses `gh release` with repository `GITHUB_TOKEN`.

[0.1.0]: https://github.com/0xNyk/lacp/releases/tag/v0.1.0
