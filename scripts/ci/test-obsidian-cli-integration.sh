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
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_OBSIDIAN_VAULT}/.obsidian" "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

# Create a test note
echo "# Test Note" > "${LACP_OBSIDIAN_VAULT}/test-note.md"

PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    echo "PASS  ${label}"
    PASS=$((PASS + 1))
  else
    echo "FAIL  ${label}  expected='${expected}' actual='${actual}'"
    FAIL=$((FAIL + 1))
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "${haystack}" | grep -q "${needle}"; then
    echo "PASS  ${label}"
    PASS=$((PASS + 1))
  else
    echo "FAIL  ${label}  expected to contain '${needle}'"
    FAIL=$((FAIL + 1))
  fi
}

# 1. Help output
help_out="$(${ROOT}/bin/lacp-obsidian-cli --help 2>&1 || true)"
assert_contains "help_output" "official Obsidian CLI" "${help_out}"

# 2. Check command (JSON) — vault should be found
check_json="$(${ROOT}/bin/lacp-obsidian-cli check --json 2>&1 || true)"
vault_status="$(echo "${check_json}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('checks', []):
    if c['name'] == 'vault_path':
        print(c['status'])
        break
" 2>/dev/null || echo "MISSING")"
assert_eq "check_vault_found" "PASS" "${vault_status}"

# 3. Check command detects missing CLI gracefully
# (Only test if obsidian is NOT on PATH — skip otherwise)
if ! command -v obsidian >/dev/null 2>&1; then
  cli_status="$(echo "${check_json}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('checks', []):
    if c['name'] == 'cli_binary':
        print(c['status'])
        break
" 2>/dev/null || echo "MISSING")"
  assert_eq "check_cli_missing" "FAIL" "${cli_status}"
else
  echo "SKIP  check_cli_missing (obsidian CLI is installed)"
fi

# 4. Doctor command (JSON)
doctor_json="$(${ROOT}/bin/lacp-obsidian-cli doctor --json 2>&1 || true)"
doctor_vault="$(echo "${doctor_json}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('checks', []):
    if c['name'] == 'vault':
        print(c['status'])
        break
" 2>/dev/null || echo "MISSING")"
assert_eq "doctor_vault_found" "PASS" "${doctor_vault}"

doctor_config="$(echo "${doctor_json}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('checks', []):
    if c['name'] == 'obsidian_config':
        print(c['status'])
        break
" 2>/dev/null || echo "MISSING")"
assert_eq "doctor_obsidian_config" "PASS" "${doctor_config}"

# 5. Doctor includes note count
assert_contains "doctor_note_count" "1 notes" "$(echo "${doctor_json}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('checks', []):
    if c['name'] == 'vault':
        print(c['detail'])
        break
" 2>/dev/null || echo "")"

# 6. Read command fails gracefully without CLI
if ! command -v obsidian >/dev/null 2>&1; then
  read_err="$(${ROOT}/bin/lacp-obsidian-cli read test-note.md 2>&1 || true)"
  assert_contains "read_requires_cli" "not found" "${read_err}"
else
  echo "SKIP  read_requires_cli (obsidian CLI is installed)"
fi

# 7. Search command fails gracefully without CLI
if ! command -v obsidian >/dev/null 2>&1; then
  search_err="$(${ROOT}/bin/lacp-obsidian-cli search "test" 2>&1 || true)"
  assert_contains "search_requires_cli" "not found" "${search_err}"
else
  echo "SKIP  search_requires_cli (obsidian CLI is installed)"
fi

# 8. Unknown subcommand
unknown_err="$(${ROOT}/bin/lacp-obsidian-cli foobar 2>&1 || true)"
assert_contains "unknown_subcommand" "Unknown subcommand" "${unknown_err}"

echo
echo "[obsidian-cli-integration-test] pass=${PASS} fail=${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
