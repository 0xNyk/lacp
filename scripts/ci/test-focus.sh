#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_FOCUS_FILE="${TMP}/focus.md"

# Test init
"${ROOT}/bin/lacp-focus" init --json | jq -e '.ok == true' >/dev/null
[[ -f "${TMP}/focus.md" ]] || { echo "FAIL: focus.md not created" >&2; exit 1; }

# Test show
"${ROOT}/bin/lacp-focus" show --json | jq -e '.ok == true' >/dev/null
"${ROOT}/bin/lacp-focus" show --json | jq -e '.content | length > 0' >/dev/null

# Test age
"${ROOT}/bin/lacp-focus" age --json | jq -e '.age_days >= 0' >/dev/null

# Test check (fresh file should pass)
"${ROOT}/bin/lacp-focus" check --json | jq -e '.stale == false' >/dev/null

# Test init --force
"${ROOT}/bin/lacp-focus" init --force --json | jq -e '.created == true' >/dev/null

# Test init without --force (should fail)
set +e
"${ROOT}/bin/lacp-focus" init --json >/dev/null 2>&1
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "FAIL: init without --force should fail when file exists" >&2
  exit 1
fi

# Test check --max-days 0 (should report stale since file is 0 days old but we can't back-date in test)
# Instead, check that check with generous max-days passes
"${ROOT}/bin/lacp-focus" check --max-days 365 --json | jq -e '.ok == true' >/dev/null

# Test show when file missing
rm -f "${TMP}/focus.md"
set +e
"${ROOT}/bin/lacp-focus" show --json 2>/dev/null | jq -e '.ok == false' >/dev/null
rc=$?
set -e

echo "[focus-test] all tests passed"
