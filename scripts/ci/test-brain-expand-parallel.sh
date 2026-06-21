#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"

export LACP_SKIP_DOTENV=1
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_KNOWLEDGE_GRAPH_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"

mkdir -p \
  "${LACP_OBSIDIAN_VAULT}" \
  "${LACP_AUTOMATION_ROOT}" \
  "${LACP_KNOWLEDGE_ROOT}" \
  "${LACP_DRAFTS_ROOT}"

PASS=0
FAIL=0

assert_eq() {
  local desc="$1"
  local expected="$2"
  local actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    echo "PASS ${desc}"
    PASS=$((PASS + 1))
  else
    echo "FAIL ${desc}"
    echo "     expected: ${expected}"
    echo "     actual:   ${actual}"
    FAIL=$((FAIL + 1))
  fi
}

assert_contains() {
  local desc="$1"
  local needle="$2"
  local haystack="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    echo "PASS ${desc}"
    PASS=$((PASS + 1))
  else
    echo "FAIL ${desc}"
    echo "     expected to contain: ${needle}"
    FAIL=$((FAIL + 1))
  fi
}

# Test 1: --help includes --sequential
HELP_OUTPUT="$("${ROOT}/bin/lacp-brain-expand" --help 2>&1 || true)"
assert_contains "--help includes --sequential" "--sequential" "${HELP_OUTPUT}"

# Test 2: --sequential flag is accepted (exits 0)
"${ROOT}/bin/lacp-brain-expand" --sequential --skip-qmd 2>/dev/null
assert_eq "--sequential flag accepted" "0" "$?"

# Test 3: default (parallel) mode runs and exits 0
"${ROOT}/bin/lacp-brain-expand" --skip-qmd 2>/dev/null
assert_eq "parallel mode (default) exits 0" "0" "$?"

# Test 4: --sequential --json produces valid JSON summary
# log() writes to stdout so we extract only the JSON object from output
JSON_OUT_RAW="$("${ROOT}/bin/lacp-brain-expand" --sequential --skip-qmd --json 2>/dev/null)"
JSON_OUT="$(echo "${JSON_OUT_RAW}" | python3 -c 'import json,sys; text=sys.stdin.read(); start=text.find("{"); d=json.loads(text[start:]) if start>=0 else {}; print(json.dumps(d))' 2>/dev/null || echo "")"
KIND="$(echo "${JSON_OUT}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["kind"])' 2>/dev/null || echo "")"
assert_eq "--sequential --json produces brain_expand JSON" "brain_expand" "${KIND}"

# Test 5: parallel --json produces valid JSON summary
# log() writes to stdout so we extract only the JSON object from output
JSON_OUT2_RAW="$("${ROOT}/bin/lacp-brain-expand" --skip-qmd --json 2>/dev/null)"
JSON_OUT2="$(echo "${JSON_OUT2_RAW}" | python3 -c 'import json,sys; text=sys.stdin.read(); start=text.find("{"); d=json.loads(text[start:]) if start>=0 else {}; print(json.dumps(d))' 2>/dev/null || echo "")"
KIND2="$(echo "${JSON_OUT2}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["kind"])' 2>/dev/null || echo "")"
assert_eq "parallel --json produces brain_expand JSON" "brain_expand" "${KIND2}"

# Test 6: --sequential JSON summary has steps (all WARN since no scripts exist)
STEP_COUNT="$(echo "${JSON_OUT}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["steps"]))' 2>/dev/null || echo "0")"
if [[ "${STEP_COUNT}" -gt 0 ]]; then
  echo "PASS sequential run records steps (got ${STEP_COUNT})"
  PASS=$((PASS + 1))
else
  echo "FAIL sequential run should record steps"
  FAIL=$((FAIL + 1))
fi

# Test 7: parallel JSON summary also has steps
STEP_COUNT2="$(echo "${JSON_OUT2}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["steps"]))' 2>/dev/null || echo "0")"
if [[ "${STEP_COUNT2}" -gt 0 ]]; then
  echo "PASS parallel run records steps (got ${STEP_COUNT2})"
  PASS=$((PASS + 1))
else
  echo "FAIL parallel run should record steps"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "brain-expand-parallel: ${PASS} passed, ${FAIL} failed"

if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
exit 0
