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
    echo "[research-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: Help works ---
"${ROOT}/bin/lacp-research" --help >/dev/null 2>&1
pass=$((pass + 1))

# --- Test 2: Surfaces lists 3 surfaces ---
count=$("${ROOT}/bin/lacp-research" surfaces --json 2>&1 | jq 'keys | length')
assert_eq "3 surfaces" "3" "${count}"

# --- Test 3: Dry run produces results ---
dry=$("${ROOT}/bin/lacp-research" run --surface sms --iterations 2 --dry-run --json 2>&1 | jq '.iterations')
assert_eq "dry run iterations" "2" "${dry}"

# --- Test 4: Dry run decisions are all dry_run ---
decisions=$("${ROOT}/bin/lacp-research" run --surface hooks --iterations 1 --dry-run --json 2>&1 | jq -r '.results[0].decision')
assert_eq "dry run decision" "dry_run" "${decisions}"

# --- Test 5: Status with no experiments ---
status=$("${ROOT}/bin/lacp-research" status --json 2>&1 | jq '.total')
[[ "${status}" -ge 0 ]] && pass=$((pass + 1)) || { echo "[research-test] FAIL status total" >&2; fail=$((fail + 1)); }

# --- Test 6: Surfaces config is valid JSON ---
jq '.' "${ROOT}/config/research/surfaces.json" >/dev/null 2>&1
pass=$((pass + 1))

# --- Test 7: Each surface has parameters array ---
valid=$("${ROOT}/bin/lacp-research" surfaces --json 2>&1 | jq 'to_entries | all(.value | has("parameters"))')
assert_eq "all surfaces have parameters" "true" "${valid}"

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[research-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[research-test] all ${total} tests passed"
