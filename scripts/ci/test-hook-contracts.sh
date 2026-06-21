#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
export HOME="${TMP}/home"
mkdir -p "${HOME}"

PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    echo "PASS: ${label}"
    PASS=$((PASS + 1))
  else
    echo "FAIL: ${label} (expected='${expected}' actual='${actual}')"
    FAIL=$((FAIL + 1))
  fi
}

# Test write + read contract
export CLAUDE_SESSION_ID="test-session-$$"
cd "${ROOT}"

python3 -c "
import sys
sys.path.insert(0, 'hooks')
from hook_contracts import SessionStartOutput, write_contract, read_contract, cleanup_contracts

# Write
out = SessionStartOutput(test_cmd='make test', git_branch='main', started_at='2026-01-01T00:00:00Z', context_budget_hint=180000)
path = write_contract('session_start', out)
assert path is not None, 'write_contract returned None'

# Read
data = read_contract('session_start')
assert data is not None, 'read_contract returned None'
assert data['test_cmd'] == 'make test', f'test_cmd mismatch: {data[\"test_cmd\"]}'
assert data['git_branch'] == 'main', f'git_branch mismatch: {data[\"git_branch\"]}'
assert data['context_budget_hint'] == 180000, f'budget mismatch: {data[\"context_budget_hint\"]}'

# Read missing
missing = read_contract('nonexistent')
assert missing is None, 'expected None for missing contract'

# Cleanup
count = cleanup_contracts()
assert count >= 1, f'expected cleanup to remove files, got {count}'

# Verify cleanup
after = read_contract('session_start')
assert after is None, 'contract should be gone after cleanup'

print('ALL_PYTHON_TESTS_PASSED')
"
result=$?
assert_eq "python contract tests" "0" "${result}"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]] || exit 1
