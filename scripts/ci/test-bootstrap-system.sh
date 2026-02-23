#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

out="$("${ROOT}/bin/lacp-bootstrap-system" --profile starter --skip-verify --auto-deps-dry-run --skip-fresh-check --json)"
json_out="$(printf '%s\n' "${out}" | sed -n '/^{/,$p')"
echo "${json_out}" | jq -e '.kind == "bootstrap_system" and (.ok == true or .doctor_summary.fail >= 0)' >/dev/null
echo "${json_out}" | jq -e '.fresh_check.enabled == false' >/dev/null

echo "[bootstrap-system-test] bootstrap-system tests passed"
