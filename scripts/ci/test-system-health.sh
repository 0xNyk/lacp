#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== test-system-health ==="

# 1. Policy file is valid JSON
echo "--- policy file ---"
if [[ -f "${ROOT}/config/system-health-policy.json" ]] && jq empty "${ROOT}/config/system-health-policy.json" >/dev/null 2>&1; then
  pass "system-health-policy.json is valid JSON"
else
  fail "system-health-policy.json missing or invalid"
fi

# 2. Policy has required top-level keys
for key in thermal load memory spotlight container_runtime rust_build ui_compositor background_processes; do
  if jq -e ".${key}" "${ROOT}/config/system-health-policy.json" >/dev/null 2>&1; then
    pass "policy has .${key}"
  else
    fail "policy missing .${key}"
  fi
done

# 3. Script exists and is executable
echo "--- binary ---"
if [[ -x "${ROOT}/bin/lacp-system-health" ]]; then
  pass "bin/lacp-system-health is executable"
else
  fail "bin/lacp-system-health missing or not executable"
fi

# 4. Help flag works
if "${ROOT}/bin/lacp-system-health" --help >/dev/null 2>&1; then
  pass "--help exits cleanly"
else
  fail "--help failed"
fi

# 5. JSON output is valid
echo "--- json output ---"
if [[ "$(uname -s)" == "Darwin" ]]; then
  json_out="$("${ROOT}/bin/lacp-system-health" --json 2>/dev/null || true)"
  if echo "${json_out}" | jq -e '.schema_version' >/dev/null 2>&1; then
    pass "JSON output has schema_version"
  else
    fail "JSON output missing schema_version"
  fi

  if echo "${json_out}" | jq -e '.kind == "system_health"' >/dev/null 2>&1; then
    pass "JSON output has kind=system_health"
  else
    fail "JSON output missing kind=system_health"
  fi

  if echo "${json_out}" | jq -e '.summary.pass >= 0' >/dev/null 2>&1; then
    pass "JSON summary has pass count"
  else
    fail "JSON summary missing pass count"
  fi

  # Check that thermal check exists in output
  if echo "${json_out}" | jq -e '.checks[] | select(.name == "system:thermal")' >/dev/null 2>&1; then
    pass "thermal check present in output"
  else
    fail "thermal check missing from output"
  fi

  # Check that load check exists
  if echo "${json_out}" | jq -e '.checks[] | select(.name == "system:load")' >/dev/null 2>&1; then
    pass "load check present in output"
  else
    fail "load check missing from output"
  fi
else
  # Non-Darwin: should skip gracefully
  json_out="$("${ROOT}/bin/lacp-system-health" --json 2>/dev/null || true)"
  if echo "${json_out}" | jq -e '.skipped == "non-darwin"' >/dev/null 2>&1; then
    pass "non-Darwin graceful skip"
  else
    fail "non-Darwin did not skip gracefully"
  fi
fi

# 6. fix-hints output includes hints array
echo "--- fix-hints ---"
if [[ "$(uname -s)" == "Darwin" ]]; then
  hints_out="$("${ROOT}/bin/lacp-system-health" --json --fix-hints 2>/dev/null || true)"
  if echo "${hints_out}" | jq -e '.remediation_hints | type == "array"' >/dev/null 2>&1; then
    pass "remediation_hints is array with --fix-hints"
  else
    fail "remediation_hints missing with --fix-hints"
  fi
fi

# 7. Doctor --system integration
echo "--- doctor --system ---"
if [[ "$(uname -s)" == "Darwin" ]]; then
  doctor_out="$("${ROOT}/bin/lacp-doctor" --system --json 2>/dev/null || true)"
  if echo "${doctor_out}" | jq -e '.checks[] | select(.name | startswith("system:"))' >/dev/null 2>&1; then
    pass "doctor --system includes system: checks"
  else
    fail "doctor --system missing system: checks"
  fi
fi

echo
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
