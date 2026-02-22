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

out="$("${ROOT}/bin/lacp-vendor-watch" --offline --state-file "${TMP}/vendor-watch-state.json" --json)"
echo "${out}" | jq -e '.kind == "vendor_watch"' >/dev/null
echo "${out}" | jq -e '.offline == true' >/dev/null
echo "${out}" | jq -e '.summary.sources_total >= 4' >/dev/null

echo "[vendor-watch-test] vendor watch tests passed"
