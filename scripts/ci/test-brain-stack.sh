#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"
export LACP_SKIP_DOTENV=1
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_OBSIDIAN_VAULT}" "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

init_json="$(${ROOT}/bin/lacp-brain-stack init --json)"
echo "${init_json}" | jq -e '.ok == true and .dry_run == false' >/dev/null
settings_path="$(echo "${init_json}" | jq -r '.claude_settings')"
[[ -f "${settings_path}" ]] || { echo "[brain-stack-test] missing settings file" >&2; exit 1; }

status_json="$(${ROOT}/bin/lacp-brain-stack status --json)"
echo "${status_json}" | jq -e '.ok == true' >/dev/null

python3 - <<'PY' "${settings_path}"
import json, sys
p = json.load(open(sys.argv[1]))
servers = p.get('mcpServers', {})
required = {'memory','smart-connections','qmd'}
missing = required - set(servers.keys())
if missing:
    raise SystemExit(f"missing mcp servers: {sorted(missing)}")
PY

echo "[brain-stack-test] brain stack tests passed"
