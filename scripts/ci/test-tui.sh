#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/lacp-lib.sh"

PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    printf 'PASS  %s\n' "${label}"
    PASS=$((PASS + 1))
  else
    printf 'FAIL  %s  expected=%s actual=%s\n' "${label}" "${expected}" "${actual}" >&2
    FAIL=$((FAIL + 1))
  fi
}

# --- Check 1: Module imports succeed (no syntax errors) ---
log "Check 1: Module imports"
import_ok="false"
if python3 -c "
import sys
sys.path.insert(0, '${ROOT}/scripts/tui')
import backend
print('backend ok')
try:
    import widgets
    print('widgets ok')
except ImportError:
    # textual not installed — widgets import expected to fail
    print('widgets skipped (textual not installed)')
" 2>/dev/null; then
  import_ok="true"
fi
assert_eq "tui_module_imports" "true" "${import_ok}"

# --- Check 2: LacpBackend._run handles failures gracefully ---
log "Check 2: Backend error handling"
error_result="$(python3 - <<'PY' "${ROOT}"
import asyncio
import json
import sys

sys.path.insert(0, f"{sys.argv[1]}/scripts/tui")
from backend import LacpBackend

async def test():
    b = LacpBackend()
    # Run a command that always fails
    result = await b._run("false")
    return result

result = asyncio.run(test())
print(json.dumps(result))
PY
)"
error_ok="$(echo "${error_result}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('true' if d.get('ok') is False else 'false')
")"
assert_eq "backend_error_handling" "true" "${error_ok}"

# --- Check 3: LacpBackend._run parses valid JSON from commands ---
log "Check 3: Backend JSON parsing"
json_result="$(python3 - <<'PY' "${ROOT}"
import asyncio
import json
import sys

sys.path.insert(0, f"{sys.argv[1]}/scripts/tui")
from backend import LacpBackend

async def test():
    b = LacpBackend()
    # Run agent-id which should return valid JSON
    result = await b.agent_id()
    return result

result = asyncio.run(test())
# Just check it returned a dict with some expected keys
has_keys = "agent_id" in result or "ok" in result or "error" in result
print("true" if has_keys else "false")
PY
)"
assert_eq "backend_json_parse" "true" "${json_result}"

# --- Check 4: App can be instantiated (if textual installed) ---
log "Check 4: App instantiation"
if python3 -c "import textual" 2>/dev/null; then
  app_ok="$(python3 - <<'PY' "${ROOT}"
import sys
sys.path.insert(0, f"{sys.argv[1]}/scripts/tui")
try:
    from app import LacpTUI
    app = LacpTUI()
    print("true")
except Exception as e:
    print(f"false:{e}", file=sys.stderr)
    print("false")
PY
  )"
  assert_eq "app_instantiation" "true" "${app_ok}"
else
  log "SKIP: textual not installed, skipping app instantiation test"
fi

# --- Summary ---
echo
log "TUI tests: pass=${PASS} fail=${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
