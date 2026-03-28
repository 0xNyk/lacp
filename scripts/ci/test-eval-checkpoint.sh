#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

HOOK="${ROOT}/hooks/eval_checkpoint.py"

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[eval-checkpoint-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_empty() {
  local label="$1" actual="$2"
  if [[ -z "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[eval-checkpoint-test] FAIL ${label}: expected empty, got='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_contains() {
  local label="$1" pattern="$2" actual="$3"
  if echo "${actual}" | grep -q "${pattern}"; then
    pass=$((pass + 1))
  else
    echo "[eval-checkpoint-test] FAIL ${label}: pattern '${pattern}' not found" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: Disabled by default (no output) ---
out1=$(echo '{}' | LACP_EVAL_CHECKPOINT_ENABLED=0 python3 "${HOOK}" 2>/dev/null) || true
assert_empty "disabled by default → no output" "${out1}"

# --- Test 2: Enabled but below interval → no output ---
out2=$(echo '{"session_id":"test-cp-1","cwd":"'"${TMP}"'"}' | \
  LACP_EVAL_CHECKPOINT_ENABLED=1 LACP_EVAL_CHECKPOINT_INTERVAL=10 \
  python3 "${HOOK}" 2>/dev/null) || true
assert_empty "below interval → no output" "${out2}"

# --- Test 3: Write counter increments ---
SESSION_STATE="${HOME}/.lacp/hooks/state/test-cp-counter"
mkdir -p "${SESSION_STATE}"
echo "9" > "${SESSION_STATE}/write-count"

# At write #10 with interval=10, should try to run tests (will fail silently with no test cmd)
out3=$(echo '{"session_id":"test-cp-counter","cwd":"'"${TMP}"'"}' | \
  LACP_EVAL_CHECKPOINT_ENABLED=1 LACP_EVAL_CHECKPOINT_INTERVAL=10 \
  CLAUDE_SESSION_ID=test-cp-counter \
  python3 "${HOOK}" 2>/dev/null) || true
# Should be empty (no test command cached → silently skips)
assert_empty "at interval but no test cmd → no output" "${out3}"

# Verify counter incremented to 10
counter=$(cat "${SESSION_STATE}/write-count" 2>/dev/null || echo "?")
assert_eq "counter incremented to 10" "10" "${counter}"

# Cleanup
rm -rf "${SESSION_STATE}"

# --- Test 4: Python compiles ---
python3 -c "import py_compile; py_compile.compile('${HOOK}', doraise=True)" 2>/dev/null
pass=$((pass + 1))

# --- Test 5: Structural checks ---
grep -q 'LACP_EVAL_CHECKPOINT_ENABLED' "${HOOK}" && pass=$((pass + 1)) || { echo "[eval-checkpoint-test] FAIL missing env var" >&2; fail=$((fail + 1)); }
grep -q 'LACP_EVAL_CHECKPOINT_INTERVAL' "${HOOK}" && pass=$((pass + 1)) || { echo "[eval-checkpoint-test] FAIL missing interval env" >&2; fail=$((fail + 1)); }
grep -q 'systemMessage' "${HOOK}" && pass=$((pass + 1)) || { echo "[eval-checkpoint-test] FAIL missing systemMessage output" >&2; fail=$((fail + 1)); }

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[eval-checkpoint-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[eval-checkpoint-test] all ${total} tests passed"
