#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_OBSIDIAN_VAULT="${TMP}/vault"

mkdir -p \
  "${HOME}" \
  "${LACP_AUTOMATION_ROOT}/scripts" \
  "${LACP_KNOWLEDGE_ROOT}" \
  "${LACP_DRAFTS_ROOT}" \
  "${LACP_OBSIDIAN_VAULT}/.obsidian/plugins/smart-connections" \
  "${LACP_OBSIDIAN_VAULT}/00-home/daily" \
  "${HOME}/.local/share/smart-connections-mcp/.venv/bin"

cat > "${LACP_AUTOMATION_ROOT}/scripts/sync_research_knowledge.py" <<'PY'
def classify_zone(score):
    if score >= 0.7:
        return "active"
    if score >= 0.3:
        return "stale"
    if score >= 0.1:
        return "fading"
    return "archived"
PY

cat > "${LACP_OBSIDIAN_VAULT}/.obsidian/plugins/smart-connections/manifest.json" <<'JSON'
{"id":"smart-connections","name":"smart-connections","version":"1.0.0"}
JSON

cat > "${HOME}/.local/share/smart-connections-mcp/server.py" <<'PY'
print("ok")
PY
chmod +x "${HOME}/.local/share/smart-connections-mcp/server.py"
touch "${HOME}/.local/share/smart-connections-mcp/.venv/bin/python"

cat > "${LACP_OBSIDIAN_VAULT}/00-home/daily/$(date +%Y-%m-%d).md" <<'MD'
# Daily
MD

cat > "${LACP_OBSIDIAN_VAULT}/recent.md" <<'MD'
# Recent
MD
touch "${LACP_OBSIDIAN_VAULT}/recent.md"

python3 - <<'PY' "${LACP_OBSIDIAN_VAULT}/recent.md"
from pathlib import Path
import os
import sys
import time

path = Path(sys.argv[1])
now = time.time()
os.utime(path, (now, now))
PY

out="$("${ROOT}/bin/lacp-brain-doctor" --json || true)"
echo "${out}" | jq -e '.ok == false or .ok == true' >/dev/null
echo "${out}" | jq -e '.checks[] | select(.name=="brain:mcp:ori_mnemos") | .status == "PASS"' >/dev/null

zone_out="$("${ROOT}/bin/lacp-brain-doctor" --zone-report --json || true)"
echo "${zone_out}" | jq -e '.checks[] | select(.name=="brain:zone_report") | .status == "PASS"' >/dev/null

echo "[brain-doctor-test] brain doctor tests passed"
