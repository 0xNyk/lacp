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

"${ROOT}/bin/lacp-pr-preflight" \
  --changed-files "${TMP}/changed-files.txt" \
  --head-sha "abc123" \
  --checks-json "${TMP}/checks-valid.json" \
  --review-json "${TMP}/review-valid.json" \
  --browser-evidence "${TMP}/browser-evidence-valid.json" \
  --json | jq -e '.ok == true and .risk_tier == "high"' >/dev/null

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

echo "[pr-preflight-test] pr preflight tests passed"
