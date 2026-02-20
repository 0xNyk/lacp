# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-02-20

### Added
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

[0.1.0]: https://github.com/0xNyk/lacp/releases/tag/v0.1.0
