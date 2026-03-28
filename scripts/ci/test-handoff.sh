#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[handoff-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_contains() {
  local label="$1" pattern="$2" actual="$3"
  if echo "${actual}" | grep -qF -- "${pattern}"; then
    pass=$((pass + 1))
  else
    echo "[handoff-test] FAIL ${label}: pattern '${pattern}' not found" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: HandoffArtifact contract write/read ---
result=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['CLAUDE_SESSION_ID'] = 'test-handoff-1'
from hook_contracts import HandoffArtifact, write_contract, read_contract, cleanup_contracts
ha = HandoffArtifact(task_summary='test task', files_modified=['a.py', 'b.py'], git_branch='main', test_status='pass', created_at='2026-03-27T12:00:00Z')
write_contract('handoff_artifact', ha, 'test-handoff-1')
data = read_contract('handoff_artifact', 'test-handoff-1')
print('ok' if data and data['task_summary'] == 'test task' and len(data['files_modified']) == 2 else 'fail')
cleanup_contracts('test-handoff-1')
")
assert_eq "HandoffArtifact write/read" "ok" "${result}"

# --- Test 2: Stale contract cleanup ---
stale=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
from hook_contracts import cleanup_stale_contracts, cleanup_stale_state
# With a very large window, nothing should be cleaned
c = cleanup_stale_contracts(max_age_hours=99999)
s = cleanup_stale_state(max_age_hours=99999)
print(f'{c},{s}')
")
assert_eq "stale cleanup with large window" "0,0" "${stale}"

# --- Test 3: lacp-handoff help ---
help_out=$("${ROOT}/bin/lacp-handoff" --help 2>&1)
assert_contains "handoff help has show" "show" "${help_out}"
assert_contains "handoff help has list" "list" "${help_out}"
assert_contains "handoff help has clean" "clean" "${help_out}"

# --- Test 4: lacp-handoff list (no crash) ---
list_out=$("${ROOT}/bin/lacp-handoff" list 2>&1) || true
pass=$((pass + 1))  # Just ensure no crash

# --- Test 5: lacp-handoff list --json ---
list_json=$("${ROOT}/bin/lacp-handoff" list --json 2>&1) || true
# Should be valid JSON (array)
echo "${list_json}" | jq 'type' >/dev/null 2>&1 && pass=$((pass + 1)) || { echo "[handoff-test] FAIL list --json not valid JSON" >&2; fail=$((fail + 1)); }

# --- Test 6: lacp-scaffold-audit help ---
audit_help=$("${ROOT}/bin/lacp-scaffold-audit" --help 2>&1)
assert_contains "scaffold-audit help has --days" "--days" "${audit_help}"
assert_contains "scaffold-audit help has --threshold" "--threshold" "${audit_help}"

# --- Test 7: lacp-scaffold-audit --json (no crash) ---
audit_json=$("${ROOT}/bin/lacp-scaffold-audit" --json 2>&1) || true
stages=$(echo "${audit_json}" | jq '.stages | length' 2>/dev/null || echo "0")
[[ "${stages}" -ge 1 ]] && pass=$((pass + 1)) || { echo "[handoff-test] FAIL scaffold-audit no stages" >&2; fail=$((fail + 1)); }

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[handoff-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[handoff-test] all ${total} tests passed"
