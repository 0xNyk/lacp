#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_FOCUS_FILE="${TMP}/focus.md"
export HOME="${TMP}"
mkdir -p "${TMP}/.lacp/provenance"

# Create a fake provenance chain with recent entries
python3 - <<'PY' "${TMP}/.lacp/provenance/chain.jsonl"
import json, sys, time
chain = sys.argv[1]
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
entries = [
    {"project_slug": "lacp", "started_at": now, "ended_at": now, "agent_id": "test-agent"},
    {"project_slug": "lacp", "started_at": now, "ended_at": now, "agent_id": "test-agent"},
    {"project_slug": "other-project", "started_at": now, "ended_at": now, "agent_id": "test-agent"},
]
with open(chain, "w") as f:
    for e in entries:
        f.write(json.dumps(e) + "\n")
PY

# Test summary subcommand
result="$("${ROOT}/bin/lacp-reflect" summary --json 2>/dev/null)"
echo "${result}" | jq -e '.ok == true' >/dev/null
echo "${result}" | jq -e '.total_sessions == 3' >/dev/null
echo "${result}" | jq -e '.projects.lacp == 2' >/dev/null

# Test prompt subcommand
result="$("${ROOT}/bin/lacp-reflect" prompt --json 2>/dev/null)"
echo "${result}" | jq -e '.ok == true' >/dev/null
echo "${result}" | jq -e '.prompts | length > 0' >/dev/null

# Test focus brief status in summary (missing)
result="$("${ROOT}/bin/lacp-reflect" summary --json 2>/dev/null)"
echo "${result}" | jq -e '.focus_brief.exists == false' >/dev/null

# Create focus brief and re-check
"${ROOT}/bin/lacp-focus" init --json >/dev/null 2>&1
result="$("${ROOT}/bin/lacp-reflect" summary --json 2>/dev/null)"
echo "${result}" | jq -e '.focus_brief.exists == true' >/dev/null

echo "[reflect-test] all tests passed"
