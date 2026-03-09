#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

LABEL="skill-orient"

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if echo "${haystack}" | grep -qF "${needle}"; then
    echo "[${LABEL}] PASS ${label}"
  else
    echo "[${LABEL}] FAIL ${label}: '${needle}' not found" >&2
    echo "--- output ---"
    echo "${haystack}"
    echo "--- end ---"
    exit 1
  fi
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if echo "${haystack}" | grep -qF "${needle}"; then
    echo "[${LABEL}] FAIL ${label}: '${needle}' should NOT be present" >&2
    exit 1
  else
    echo "[${LABEL}] PASS ${label}"
  fi
}

# --- Setup: mock knowledge root ---
export LACP_ROOT="${ROOT}"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
mkdir -p "${LACP_KNOWLEDGE_ROOT}/data/workflows/brain-expand"
mkdir -p "${LACP_KNOWLEDGE_ROOT}/data/gap-detection"
mkdir -p "${LACP_KNOWLEDGE_ROOT}/data/review-queue"

# --- Test 1: No ledger = no skill hints ---
REAL_LEDGER="${HOME}/.agents/skills/auto-skill-factory/state/workflow_ledger.json"
BACKUP=""

# Temporarily hide real ledger if it exists
if [[ -f "${REAL_LEDGER}" ]]; then
  BACKUP="${TMP}/ledger_backup.json"
  cp "${REAL_LEDGER}" "${BACKUP}"
  mv "${REAL_LEDGER}" "${REAL_LEDGER}.test-bak"
fi

restore_ledger() {
  if [[ -n "${BACKUP}" && -f "${REAL_LEDGER}.test-bak" ]]; then
    mv "${REAL_LEDGER}.test-bak" "${REAL_LEDGER}"
  fi
}
trap 'restore_ledger; rm -rf "${TMP}"' EXIT

out="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"
assert_not_contains "${out}" "Proven workflows" "no_ledger_no_hints"

# --- Test 2: Small ledger (<5 workflows) = no hints ---
MOCK_LEDGER_DIR="$(dirname "${REAL_LEDGER}")"
mkdir -p "${MOCK_LEDGER_DIR}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

cat > "${REAL_LEDGER}" <<JSON
{
  "version": 1,
  "updated_at": "${NOW}",
  "workflows": {
    "wf-a": {"signature": "small-a", "purpose": "test", "count": 1, "success_count": 1, "confidence": 0.5, "last_seen": "${NOW}"},
    "wf-b": {"signature": "small-b", "purpose": "test", "count": 1, "success_count": 1, "confidence": 0.5, "last_seen": "${NOW}"}
  }
}
JSON

out2="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"
assert_not_contains "${out2}" "Proven workflows" "small_ledger_no_hints"

# --- Test 3: Ledger with 5+ high-confidence workflows = shows hints ---
cat > "${REAL_LEDGER}" <<JSON
{
  "version": 1,
  "updated_at": "${NOW}",
  "workflows": {
    "wf-1": {"signature": "run tests after changes", "purpose": "run tests after code changes", "count": 10, "success_count": 10, "confidence": 0.95, "last_seen": "${NOW}", "sessions": []},
    "wf-2": {"signature": "lint before commit", "purpose": "lint code before committing", "count": 8, "success_count": 7, "confidence": 0.82, "last_seen": "${NOW}", "sessions": []},
    "wf-3": {"signature": "build docker image", "purpose": "build container image", "count": 6, "success_count": 6, "confidence": 0.78, "last_seen": "${NOW}", "sessions": []},
    "wf-4": {"signature": "deploy staging", "purpose": "deploy to staging env", "count": 5, "success_count": 4, "confidence": 0.65, "last_seen": "${NOW}", "sessions": []},
    "wf-5": {"signature": "update deps", "purpose": "update project dependencies", "count": 4, "success_count": 4, "confidence": 0.55, "last_seen": "${NOW}", "sessions": []},
    "wf-low": {"signature": "debug thing", "purpose": "one-off debug", "count": 1, "success_count": 0, "confidence": 0.1, "last_seen": "${NOW}", "sessions": []}
  }
}
JSON

out3="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"
assert_contains "${out3}" "Proven workflows" "large_ledger_shows_hints"
assert_contains "${out3}" "run tests after changes" "top_workflow_shown"

# --- Test 4: Low-confidence workflows not shown ---
assert_not_contains "${out3}" "debug thing" "low_conf_filtered"

# Restore real ledger
restore_ledger
BACKUP=""

echo "[${LABEL}] all skill-orient tests passed"
