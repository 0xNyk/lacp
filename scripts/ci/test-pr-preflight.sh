#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# Changed files trigger high tier and satisfy docs drift requirement.
cat > "${TMP}/changed-files.txt" <<'EOF2'
bin/lacp
scripts/runners/tmux-runner.sh
docs/runbook.md
EOF2

# Checks include required checks for high tier and match head sha.
cat > "${TMP}/checks-valid.json" <<'EOF2'
{
  "check_runs": [
    {"name": "risk-policy-gate", "status": "completed", "conclusion": "success", "head_sha": "abc123"},
    {"name": "harness-smoke", "status": "completed", "conclusion": "success", "head_sha": "abc123"},
    {"name": "Browser Evidence", "status": "completed", "conclusion": "success", "head_sha": "abc123"},
    {"name": "CI Pipeline", "status": "completed", "conclusion": "success", "head_sha": "abc123"}
  ]
}
EOF2

cat > "${TMP}/review-valid.json" <<'EOF2'
{
  "head_sha": "abc123",
  "status": "success",
  "actionable_findings": 0
}
EOF2

mkdir -p "${TMP}/artifacts"
touch "${TMP}/artifacts/trace.zip" "${TMP}/artifacts/screen.png"
cat > "${TMP}/browser-evidence-valid.json" <<EOF2
{
  "version": "1",
  "captured_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "flows": [
    {
      "id": "flow-ui-main",
      "entrypoint_kind": "ui-flow",
      "entrypoint": "/",
      "expected_identity": {"mode": "user", "value": "qa-user"},
      "artifacts": {
        "trace": "${TMP}/artifacts/trace.zip",
        "screenshot": "${TMP}/artifacts/screen.png"
      },
      "assertions": [{"name": "home loaded", "ok": true}]
    },
    {
      "id": "flow-auth-main",
      "entrypoint_kind": "auth-flow",
      "entrypoint": "/api/auth",
      "expected_identity": {"mode": "service", "value": "svc-auth"},
      "artifacts": {
        "trace": "${TMP}/artifacts/trace.zip",
        "screenshot": "${TMP}/artifacts/screen.png"
      },
      "assertions": [{"name": "auth ok", "ok": true}]
    }
  ]
}
EOF2

cat > "${TMP}/api-evidence-valid.json" <<EOF2
{
  "version": "1",
  "captured_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "flows": [
    {
      "id": "api-authz-guest",
      "entrypoint_kind": "api-flow",
      "entrypoint": "/api/private/orders",
      "expected_identity": {"mode": "guest", "value": "anon"},
      "artifacts": {
        "trace": "${TMP}/artifacts/trace.zip",
        "screenshot": "${TMP}/artifacts/screen.png"
      },
      "assertions": [{"name": "http status 401 unauthorized", "ok": true}]
    }
  ]
}
EOF2

cat > "${TMP}/contract-evidence-valid.json" <<EOF2
{
  "version": "1",
  "captured_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "flows": [
    {
      "id": "contract-invariant-main",
      "entrypoint_kind": "contract-flow",
      "entrypoint": "ERC20.transfer",
      "expected_identity": {"mode": "service", "value": "ci-contract-runner"},
      "artifacts": {
        "trace": "${TMP}/artifacts/trace.zip",
        "screenshot": "${TMP}/artifacts/screen.png"
      },
      "assertions": [{"name": "invariant totalSupply preserved", "ok": true}]
    }
  ]
}
EOF2

cat > "${TMP}/flows-auto.json" <<EOF2
[
  {
    "id": "flow-ui-main",
    "entrypoint_kind": "ui-flow",
    "entrypoint": "/",
    "expected_identity": {"mode": "user", "value": "qa-user"},
    "artifacts": {
      "trace": "${TMP}/artifacts/trace.zip",
      "screenshot": "${TMP}/artifacts/screen.png"
    },
    "assertions": [{"name": "auth session present", "ok": true}]
  },
  {
    "id": "flow-auth-main",
    "entrypoint_kind": "auth-flow",
    "entrypoint": "/api/auth",
    "expected_identity": {"mode": "guest", "value": "anon"},
    "artifacts": {
      "trace": "${TMP}/artifacts/trace.zip",
      "screenshot": "${TMP}/artifacts/screen.png"
    },
    "assertions": [{"name": "auth denied when guest", "ok": true}]
  }
]
EOF2

"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --json | jq -e '.ok == true and .risk_tier == "high"' >/dev/null

"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --auto-e2e-run \
  --auto-e2e-command "/bin/echo playwright-stub-ok" \
  --auto-e2e-flows-file "${TMP}/flows-auto.json" \
  --auto-e2e-manifest "${TMP}/browser-evidence-auto.json" \
  --auto-e2e-auth-check \
  --json | jq -e '.ok == true and .browser_evidence.auto_e2e.ok == true and .browser_evidence.auto_e2e.auth_check.ok == true' >/dev/null

# stale head sha in review/checks should fail.
cat > "${TMP}/review-stale.json" <<'EOF2'
{
  "head_sha": "oldsha",
  "status": "success",
  "actionable_findings": 0
}
EOF2

set +e
"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-stale.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[pr-preflight-test] FAIL expected stale review state to fail (rc=1), got ${rc}" >&2
  exit 1
fi

# docs drift missing docs update should fail.
cat > "${TMP}/changed-files-docs-missing.txt" <<'EOF2'
bin/lacp
EOF2

set +e
"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-docs-missing.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[pr-preflight-test] FAIL expected docs drift failure (rc=1), got ${rc}" >&2
  exit 1
fi

# medium tier now requires browser evidence as baseline.
cat > "${TMP}/changed-files-medium.txt" <<'EOF2'
config/harness/tasks.schema.json
docs/runbook.md
EOF2

set +e
"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-medium.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[pr-preflight-test] FAIL expected medium tier to require browser evidence (rc=1), got ${rc}" >&2
  exit 1
fi

# API path scope should require api evidence when tier matches.
cat > "${TMP}/changed-files-api.txt" <<'EOF2'
app/api/orders.ts
EOF2

set +e
"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-api.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --json > "${TMP}/api-missing.json"
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[pr-preflight-test] FAIL expected api scope to require api evidence (rc=1), got ${rc}" >&2
  exit 1
fi
jq -e '.api_evidence.required == true and .api_evidence.ok == false' "${TMP}/api-missing.json" >/dev/null

"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-api.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --api-evidence "${TMP}/api-evidence-valid.json" \
  --json | jq -e '.ok == true and .api_evidence.required == true and .api_evidence.ok == true' >/dev/null

# Contract path scope should require contract evidence when tier matches.
cat > "${TMP}/changed-files-contract.txt" <<'EOF2'
contracts/token.sol
EOF2

set +e
"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-contract.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --json > "${TMP}/contract-missing.json"
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[pr-preflight-test] FAIL expected contract scope to require contract evidence (rc=1), got ${rc}" >&2
  exit 1
fi
jq -e '.contract_evidence.required == true and .contract_evidence.ok == false' "${TMP}/contract-missing.json" >/dev/null

"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files-contract.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --contract-evidence "${TMP}/contract-evidence-valid.json" \
  --json | jq -e '.ok == true and .contract_evidence.required == true and .contract_evidence.ok == true' >/dev/null

echo "[pr-preflight-test] pr preflight tests passed"
