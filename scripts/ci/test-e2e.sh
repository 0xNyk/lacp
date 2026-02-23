#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/artifacts"
touch "${TMP}/artifacts/trace.zip" "${TMP}/artifacts/screen.png"

cat > "${TMP}/flows.json" <<EOF2
[
  {
    "id": "ui-main",
    "entrypoint_kind": "ui-flow",
    "entrypoint": "/",
    "expected_identity": {"mode": "user", "value": "qa-user"},
    "artifacts": {
      "trace": "${TMP}/artifacts/trace.zip",
      "screenshot": "${TMP}/artifacts/screen.png"
    },
    "assertions": [{"name": "auth cookie present", "ok": true}]
  },
  {
    "id": "auth-main",
    "entrypoint_kind": "auth-flow",
    "entrypoint": "/api/auth/session",
    "expected_identity": {"mode": "guest", "value": "anon"},
    "artifacts": {
      "trace": "${TMP}/artifacts/trace.zip",
      "screenshot": "${TMP}/artifacts/screen.png"
    },
    "assertions": [{"name": "auth denied for guest", "ok": true}]
  }
]
EOF2

"${ROOT}/bin/lacp-e2e" run \
  --command "/bin/echo playwright stub run" \
  --workdir "${ROOT}" \
  --flows-file "${TMP}/flows.json" \
  --manifest "${TMP}/browser-evidence.json" \
  --json | jq -e '.ok == true and .command.exit_code == 0' >/dev/null

"${ROOT}/bin/lacp-e2e" auth-check \
  --manifest "${TMP}/browser-evidence.json" \
  --require-entrypoint-kind auth-flow \
  --require-entrypoint-kind ui-flow \
  --require-identity-mode guest \
  --require-identity-mode user \
  --require-assertion-substring auth \
  --json | jq -e '.ok == true' >/dev/null

set +e
"${ROOT}/bin/lacp-e2e" auth-check \
  --manifest "${TMP}/browser-evidence.json" \
  --require-assertion-substring csrf \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[e2e-test] FAIL expected auth-check failure when assertion token missing, got rc=${rc}" >&2
  exit 1
fi

mkdir -p "${TMP}/smoke/.lacp/e2e-artifacts"
touch "${TMP}/smoke/.lacp/e2e-artifacts/ui-smoke-home.trace.zip"
touch "${TMP}/smoke/.lacp/e2e-artifacts/ui-smoke-home.png"
touch "${TMP}/smoke/.lacp/e2e-artifacts/auth-smoke-session.trace.zip"
touch "${TMP}/smoke/.lacp/e2e-artifacts/auth-smoke-session.png"

"${ROOT}/bin/lacp-e2e" smoke \
  --workdir "${TMP}/smoke" \
  --init-template \
  --skip-command \
  --example-flows "${ROOT}/config/harness/e2e-flows.example.json" \
  --json | jq -e '.ok == true and .init_template.applied == true and .auth_check.ok == true' >/dev/null

echo "[e2e-test] e2e command tests passed"
