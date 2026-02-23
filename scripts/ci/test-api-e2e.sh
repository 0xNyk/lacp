#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/artifacts"
touch "${TMP}/artifacts/api.trace.txt" "${TMP}/artifacts/api.report.txt"

cat > "${TMP}/flows.json" <<EOF2
[
  {
    "id": "api-main",
    "entrypoint_kind": "api-flow",
    "entrypoint": "/api/orders",
    "expected_identity": {"mode":"user","value":"qa-user"},
    "artifacts": {
      "trace": "${TMP}/artifacts/api.trace.txt",
      "screenshot": "${TMP}/artifacts/api.report.txt"
    },
    "assertions": [{"name":"http status 200", "ok": true}]
  }
]
EOF2

"${ROOT}/bin/lacp-api-e2e" run \
  --command "/bin/echo api e2e stub" \
  --workdir "${ROOT}" \
  --flows-file "${TMP}/flows.json" \
  --manifest "${TMP}/api-evidence.json" \
  --json | jq -e '.ok == true and .api_check.ok == true' >/dev/null

mkdir -p "${TMP}/smoke/.lacp/e2e-artifacts"
touch "${TMP}/smoke/.lacp/e2e-artifacts/api-authz-guest-denied.trace.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/api-authz-guest-denied.report.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/api-user-orders-ok.trace.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/api-user-orders-ok.report.txt"

"${ROOT}/bin/lacp-api-e2e" smoke \
  --workdir "${TMP}/smoke" \
  --init-template \
  --skip-command \
  --example-flows "${ROOT}/config/harness/api-e2e-flows.example.json" \
  --json | jq -e '.ok == true and .init_template.applied == true and .run.ok == true' >/dev/null

echo "[api-e2e-test] api e2e command tests passed"
