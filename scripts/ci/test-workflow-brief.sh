#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1

fail() { echo "[workflow-brief-test] FAIL: $1" >&2; exit 1; }

run_hook() {
  # SessionStart hook reads JSON on stdin, emits JSON on stdout. Run from a
  # scratch HOME so unrelated focus/handoff/memory state can't interfere.
  echo '{"matcher":""}' | HOME="${TMP}/home" "$@" python3 "${ROOT}/hooks/session_start.py" 2>/dev/null || true
}

mkdir -p "${TMP}/home"

# ---------- 1. LACP_WORKFLOW=gstack -> brief injected ----------
out="$(run_hook env LACP_WORKFLOW=gstack)"
echo "${out}" | grep -q "Workflow (gstack)" || fail "gstack brief not injected when LACP_WORKFLOW=gstack"
echo "${out}" | grep -q "plan-ceo-review" || fail "gstack brief missing the 6-command flow"

# ---------- 2. unset -> no brief (no-op) ----------
out="$(run_hook env)"
if echo "${out}" | grep -q "Workflow (gstack)"; then
  fail "gstack brief injected when LACP_WORKFLOW unset"
fi

# ---------- 3. unknown value -> no brief ----------
out="$(run_hook env LACP_WORKFLOW=banana)"
if echo "${out}" | grep -q "Workflow (gstack)"; then
  fail "gstack brief injected for an unknown LACP_WORKFLOW value"
fi

# ---------- 4. case-insensitive ----------
out="$(run_hook env LACP_WORKFLOW=GStack)"
echo "${out}" | grep -q "Workflow (gstack)" || fail "LACP_WORKFLOW match is not case-insensitive"

echo "[workflow-brief-test] all workflow-brief tests passed"
