#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/artifacts"
touch "${TMP}/artifacts/contract.trace.txt" "${TMP}/artifacts/contract.report.txt"

cat > "${TMP}/flows.json" <<EOF2
[
  {
    "id": "contract-main",
    "entrypoint_kind": "contract-flow",
    "entrypoint": "ERC20.transfer",
    "expected_identity": {"mode":"service","value":"ci-contract-runner"},
    "artifacts": {
      "trace": "${TMP}/artifacts/contract.trace.txt",
      "screenshot": "${TMP}/artifacts/contract.report.txt"
    },
    "assertions": [{"name":"invariant balance preserved", "ok": true}]
  }
]
EOF2

"${ROOT}/bin/lacp-contract-e2e" run \
  --command "/bin/echo contract e2e stub" \
  --workdir "${ROOT}" \
  --flows-file "${TMP}/flows.json" \
  --manifest "${TMP}/contract-evidence.json" \
  --json | jq -e '.ok == true and .contract_check.ok == true' >/dev/null

mkdir -p "${TMP}/smoke/.lacp/e2e-artifacts"
touch "${TMP}/smoke/.lacp/e2e-artifacts/contract-transfer-invariant.trace.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/contract-transfer-invariant.report.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/contract-revert-unauthorized.trace.txt"
touch "${TMP}/smoke/.lacp/e2e-artifacts/contract-revert-unauthorized.report.txt"

"${ROOT}/bin/lacp-contract-e2e" smoke \
  --workdir "${TMP}/smoke" \
  --init-template \
  --skip-command \
  --example-flows "${ROOT}/config/harness/contract-e2e-flows.example.json" \
  --json | jq -e '.ok == true and .init_template.applied == true and .run.ok == true' >/dev/null

echo "[contract-e2e-test] contract e2e command tests passed"
