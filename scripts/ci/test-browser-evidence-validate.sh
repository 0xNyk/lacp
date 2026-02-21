#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/artifacts"
touch "${TMP}/artifacts/flow.trace.zip"
touch "${TMP}/artifacts/flow.png"

cat > "${TMP}/manifest-valid.json" <<EOF2
{
  "version": "1",
  "captured_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "flows": [
    {
      "id": "ui-login-flow",
      "entrypoint_kind": "ui-flow",
      "entrypoint": "/login",
      "expected_identity": {"mode": "user", "value": "qa-user"},
      "artifacts": {
        "trace": "${TMP}/artifacts/flow.trace.zip",
        "screenshot": "${TMP}/artifacts/flow.png"
      },
      "assertions": [
        {"name": "loads login", "ok": true}
      ]
    },
    {
      "id": "auth-refresh-flow",
      "entrypoint_kind": "auth-flow",
      "entrypoint": "/api/auth/refresh",
      "expected_identity": {"mode": "service", "value": "api-worker"},
      "artifacts": {
        "trace": "${TMP}/artifacts/flow.trace.zip",
        "screenshot": "${TMP}/artifacts/flow.png"
      },
      "assertions": [
        {"name": "refresh token accepted", "ok": true}
      ]
    }
  ]
}
EOF2

"${ROOT}/bin/lacp-browser-evidence-validate" \
  --manifest "${TMP}/manifest-valid.json" \
  --required-entrypoint-kind ui-flow \
  --required-entrypoint-kind auth-flow \
  --max-age-hours 24 \
  --json >/dev/null

cat > "${TMP}/manifest-invalid.json" <<'EOF2'
{
  "version": "1",
  "captured_at_utc": "2025-01-01T00:00:00Z",
  "flows": [
    {
      "id": "broken-flow",
      "entrypoint_kind": "ui-flow",
      "entrypoint": "/broken",
      "expected_identity": {"mode": "user", "value": "qa-user"},
      "artifacts": {
        "trace": "missing.trace.zip",
        "screenshot": "missing.png"
      },
      "assertions": [
        {"name": "broken assertion", "ok": false}
      ]
    }
  ]
}
EOF2

set +e
"${ROOT}/bin/lacp-browser-evidence-validate" \
  --manifest "${TMP}/manifest-invalid.json" \
  --required-entrypoint-kind auth-flow \
  --max-age-hours 24 \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[browser-evidence-test] FAIL expected invalid manifest rc=1, got ${rc}" >&2
  exit 1
fi

echo "[browser-evidence-test] browser evidence validation tests passed"
