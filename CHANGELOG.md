# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-02-20

### Added
- `bin/lacp` top-level CLI dispatcher (`start/install/doctor/test/...`).
- `bin/lacp-incident-drill` for scenario-based incident readiness checks with artifacts.
- `bin/lacp-cache-audit` to track prompt cache effectiveness from local Claude/Codex history logs.
- Cache audit upgraded to parse provider-native schemas (`.codex/sessions` token_count and `.claude/projects` assistant usage).
- `bin/lacp-cache-guard` to enforce minimum cache hit-rate and usage-event thresholds.
- `bin/lacp-skill-audit` to detect high-risk skill supply-chain patterns (`curl|bash`, reverse shell signatures, etc.).
- `bin/lacp-release-gate` for one-command pre-live go/no-go checks across tests, doctor, cache, and skill audit.
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

[0.1.0]: https://github.com/0xNyk/lacp/releases/tag/v0.1.0
