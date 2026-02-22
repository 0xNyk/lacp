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

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter >/dev/null

out="$("/bin/bash" "${ROOT}/bin/lacp-canary-optimize" --iterations 1 --hours 1 --days 1 --no-apply-env --json)"
json_out="$(printf '%s\n' "${out}" | sed -n '/^{/,$p')"

echo "${json_out}" | jq -e '.kind == "canary_optimize"' >/dev/null
echo "${json_out}" | jq -e '.ok == true' >/dev/null
echo "${json_out}" | jq -e '.attempts | length >= 1' >/dev/null

echo "[canary-optimize-test] canary optimize tests passed"
