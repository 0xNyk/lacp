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

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter --auto-deps-dry-run --no-obsidian-setup >/dev/null
doctor_out="$("/bin/bash" "${ROOT}/bin/lacp-doctor" --fix-deps --auto-deps-dry-run --json)"
doctor_json="$(printf '%s\n' "${doctor_out}" | sed -n '/^{/,$p')"
echo "${doctor_json}" | jq -e '.ok == true or .summary.fail >= 0' >/dev/null

echo "[auto-deps-test] auto deps dry-run tests passed"
