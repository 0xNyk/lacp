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
    echo "[tools-registry-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: JSON output returns array ---
type_check=$("${ROOT}/bin/lacp-tools" --json 2>&1 | jq 'type')
assert_eq "json output is array" '"array"' "${type_check}"

# --- Test 2: At least 50 commands ---
count=$("${ROOT}/bin/lacp-tools" --json 2>&1 | jq 'length')
[[ "${count}" -ge 50 ]] && pass=$((pass + 1)) || { echo "[tools-registry-test] FAIL count ${count} < 50" >&2; fail=$((fail + 1)); }

# --- Test 3: Each entry has required fields ---
valid=$("${ROOT}/bin/lacp-tools" --json 2>&1 | jq 'all(has("name", "description", "category", "json_output"))')
assert_eq "all entries have required fields" "true" "${valid}"

# --- Test 4: Filter works ---
filtered=$("${ROOT}/bin/lacp-tools" --filter doctor --json 2>&1 | jq 'length')
[[ "${filtered}" -ge 1 ]] && pass=$((pass + 1)) || { echo "[tools-registry-test] FAIL filter returned 0 results" >&2; fail=$((fail + 1)); }

# --- Test 5: MCP output has tools array ---
mcp_count=$("${ROOT}/bin/lacp-tools" --mcp 2>&1 | jq '.tools | length')
[[ "${mcp_count}" -ge 50 ]] && pass=$((pass + 1)) || { echo "[tools-registry-test] FAIL MCP tools count ${mcp_count} < 50" >&2; fail=$((fail + 1)); }

# --- Test 6: MCP tool has name and description ---
mcp_valid=$("${ROOT}/bin/lacp-tools" --mcp 2>&1 | jq '.tools | all(has("name", "description", "inputSchema"))')
assert_eq "MCP tools have required fields" "true" "${mcp_valid}"

# --- Test 7: Text output works ---
text_out=$("${ROOT}/bin/lacp-tools" --text 2>&1)
echo "${text_out}" | grep -qF "commands total" && pass=$((pass + 1)) || { echo "[tools-registry-test] FAIL text output missing total" >&2; fail=$((fail + 1)); }

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[tools-registry-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[tools-registry-test] all ${total} tests passed"
