# LACP Optimization Audit (2026-02-20)

## Summary

LACP is in good shape as a local control plane MVP. The next improvements should focus on:
- stronger repository hygiene standards
- non-interactive remote provider readiness
- deterministic CI validation
- tighter telemetry contracts for cost/latency

## Web-Backed Findings

1. Repository quality signals should be explicit and standardized.
- Add structured project metadata and contribution expectations.
- Add a dedicated security reporting process.

2. Sandboxing providers emphasize clear lifecycle controls and isolation contracts.
- Keep provider adapters explicit and auditable.
- Favor deterministic CLI/API flows over interactive setup in automation paths.

3. Observability should converge toward unified traces/metrics/logs.
- Track run-level latency, failure class, and provider cost metadata in one artifact schema.

## Local Framework Findings

### Strengths

- Clear separation: control plane vs runtime.
- Policy-based routing is implemented and explainable.
- Dry-run + JSON outputs are in place for safe automation.
- Verification and doctor commands provide fast operator feedback.

### Gaps

1. No CI pipeline in this repo yet.
- Scripts are validated manually; no automated checks on push/PR.

2. No standardized contribution/security docs.
- Missing `SECURITY.md` and `CONTRIBUTING.md`.

3. E2B adapter is in existing-sandbox mode only.
- Needs non-interactive create/exec/destroy path once CLI/API flow is confirmed.

4. Remote setup does not validate end-to-end command execution post-auth.
- It configures and advises, but does not run a full provider smoke test.

5. Cost/latency telemetry for remote runs is minimal.
- Current run artifacts capture route/runner/exit status but not provider cost fields.

## Prioritized Plan

### P0

1. Add CI workflow:
- shell syntax checks for all scripts
- `shellcheck` gates
- smoke tests for `lacp-route`, `lacp-doctor`, `lacp-sandbox-run --dry-run`

2. Add repository governance docs:
- `SECURITY.md` (vulnerability reporting + secret handling)
- `CONTRIBUTING.md` (workflow + conventions + validation commands)

3. Add provider health checks to `lacp-doctor`:
- daytona auth check (`daytona list --format json`)
- e2b readiness check (cli presence + key/env contract)

### P1

1. Standardize run artifact schema versioning:
- add `schema_version`
- add `duration_ms`
- add provider-specific metadata object

2. Add `lacp-remote-smoke`:
- dry-run and live modes
- validates provider auth and executes a trivial command
- writes result artifact

3. Add policy tests:
- deterministic fixtures for route decisions

Status update (2026-02-20):
- `schema_version`, `duration_ms`, and provider metadata are now implemented in:
  - `bin/lacp-sandbox-run` artifacts
  - `bin/lacp-remote-smoke` artifacts

### P2

1. E2B lifecycle runner:
- create -> exec -> cleanup (non-interactive)

2. Optional OpenTelemetry export:
- spans for route decision, runner dispatch, command execution

## Sources

- GitHub Docs (README / project guidance): https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
- GitHub Docs (security policy): https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository
- Daytona CLI docs: https://docs.daytona.io/
- E2B sandbox docs: https://e2b.dev/docs/sandbox
- Modal sandbox/files docs: https://modal.com/docs/guide/sandbox-files
- OpenTelemetry docs: https://opentelemetry.io/docs/
