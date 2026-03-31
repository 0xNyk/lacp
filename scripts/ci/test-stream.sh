#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[stream-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_contains() {
  local label="$1" pattern="$2" actual="$3"
  if echo "${actual}" | grep -qF -- "${pattern}"; then
    pass=$((pass + 1))
  else
    echo "[stream-test] FAIL ${label}: pattern '${pattern}' not found" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: Help text ---
help_out=$("${ROOT}/bin/lacp-stream" --help 2>&1)
assert_contains "help has --agent" "--agent" "${help_out}"
assert_contains "help has --mode" "--mode" "${help_out}"
assert_contains "help has --resume" "--resume" "${help_out}"

# --- Test 2: JSON output (dry run) ---
json_out=$("${ROOT}/bin/lacp-stream" --json 2>&1)
agent_path=$(echo "${json_out}" | jq -r '.agent_path')
[[ -n "${agent_path}" && "${agent_path}" != "null" ]] && pass=$((pass + 1)) || { echo "[stream-test] FAIL json agent_path missing" >&2; fail=$((fail + 1)); }

# --- Test 3: Context mode validation ---
bad_mode=$("${ROOT}/bin/lacp-stream" --mode nonexistent --dry-run 2>&1) || true
assert_contains "bad mode dies" "Unknown context mode" "${bad_mode}"

# --- Test 4: TDD mode enables eval checkpoint ---
tdd_json=$("${ROOT}/bin/lacp-stream" --mode tdd --json 2>&1)
eval_cp=$(echo "${tdd_json}" | jq -r '.eval_checkpoint')
assert_eq "tdd enables eval checkpoint" "true" "${eval_cp}"

# --- Test 5: Sprint mode enables eval checkpoint ---
sprint_json=$("${ROOT}/bin/lacp-stream" --mode sprint --json 2>&1)
eval_cp2=$(echo "${sprint_json}" | jq -r '.eval_checkpoint')
assert_eq "sprint enables eval checkpoint" "true" "${eval_cp2}"

# --- Test 6: Debugging mode enables eval checkpoint ---
debug_json=$("${ROOT}/bin/lacp-stream" --mode debugging --json 2>&1)
eval_cp3=$(echo "${debug_json}" | jq -r '.eval_checkpoint')
assert_eq "debugging enables eval checkpoint" "true" "${eval_cp3}"

# --- Test 7: Verification mode enables eval checkpoint ---
verify_json=$("${ROOT}/bin/lacp-stream" --mode verification --json 2>&1)
eval_cp4=$(echo "${verify_json}" | jq -r '.eval_checkpoint')
assert_eq "verification enables eval checkpoint" "true" "${verify_cp4:-${eval_cp4}}"

# --- Test 8: Default mode does NOT enable eval checkpoint ---
default_json=$("${ROOT}/bin/lacp-stream" --json 2>&1)
eval_cp5=$(echo "${default_json}" | jq -r '.eval_checkpoint')
assert_eq "default no eval checkpoint" "false" "${eval_cp5}"

# --- Test 9: Resume flag ---
resume_json=$("${ROOT}/bin/lacp-stream" --resume --json 2>&1)
resume_val=$(echo "${resume_json}" | jq -r '.resume')
assert_eq "resume flag" "true" "${resume_val}"

# --- Test 10: Dry run output ---
dry_out=$("${ROOT}/bin/lacp-stream" --dry-run 2>&1)
assert_contains "dry run shows command" "Would run" "${dry_out}"

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[stream-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[stream-test] all ${total} tests passed"
