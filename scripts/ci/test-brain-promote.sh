#!/usr/bin/env bash
set -euo pipefail

# Tests for brain-promote: capture-promote pipeline lifecycle.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

PASS_COUNT=0
FAIL_COUNT=0

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[brain-promote] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[brain-promote] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

# Setup mock vault
MOCK_VAULT="${TMP}/vault"
MOCK_INBOX="${MOCK_VAULT}/inbox"
mkdir -p "${MOCK_INBOX}" "${MOCK_VAULT}/knowledge"

export LACP_OBSIDIAN_VAULT="${MOCK_VAULT}"
export LACP_SKIP_DOTENV="1"

# --- Test 1: Basic promote lifecycle ---
echo "--- Test 1: Basic promote lifecycle ---"
cat > "${MOCK_INBOX}/test-note.md" <<'EOF'
---
status: inbox
title: Test Note
---
This is a test note about a [[decision]] I made.
I also reference [[project-alpha]].
EOF

result="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/test-note.md" --json 2>/dev/null)"
status_change="$(echo "${result}" | python3 -c "import json,sys; print(json.load(sys.stdin)['status_change'])")"
moved="$(echo "${result}" | python3 -c "import json,sys; print(json.load(sys.stdin)['moved'])")"
note_type="$(echo "${result}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type'])")"

assert_eq "${status_change}" "inbox -> active" "promote_status_change"
assert_eq "${moved}" "True" "promote_file_moved"
# Source file should be gone
assert_eq "$(test -f "${MOCK_INBOX}/test-note.md" && echo "exists" || echo "gone")" "gone" "promote_source_removed"

# --- Test 2: Auto-classification ---
echo "--- Test 2: Auto-classification ---"

# Decision note
cat > "${MOCK_INBOX}/decision-note.md" <<'EOF'
---
status: inbox
---
We decided to use PostgreSQL over MongoDB. The decision was based on ACID compliance.
EOF

result2="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/decision-note.md" --json 2>/dev/null)"
type2="$(echo "${result2}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type'])")"
auto2="$(echo "${result2}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type_auto_classified'])")"
assert_eq "${type2}" "decision" "auto_classify_decision"
assert_eq "${auto2}" "True" "auto_classify_flag_true"

# Blocker note
cat > "${MOCK_INBOX}/blocker-note.md" <<'EOF'
---
status: inbox
---
Blocked by failing CI. The build is broken and cannot deploy.
EOF

result3="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/blocker-note.md" --json 2>/dev/null)"
type3="$(echo "${result3}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type'])")"
assert_eq "${type3}" "blocker" "auto_classify_blocker"

# --- Test 3: Wiki-link detection ---
echo "--- Test 3: Wiki-link detection ---"
cat > "${MOCK_INBOX}/links-note.md" <<'EOF'
---
status: inbox
---
See [[project-alpha]] and [[design-doc|Design Document]] for context.
Also check [[reference#section]].
EOF

result4="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/links-note.md" --json 2>/dev/null)"
link_count="$(echo "${result4}" | python3 -c "import json,sys; print(json.load(sys.stdin)['link_count'])")"
assert_eq "${link_count}" "3" "wiki_link_detection_count"

# --- Test 4: Dry-run mode ---
echo "--- Test 4: Dry-run mode ---"
cat > "${MOCK_INBOX}/dry-run-note.md" <<'EOF'
---
status: inbox
---
This note should not be moved.
EOF

result5="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/dry-run-note.md" --dry-run --json 2>/dev/null)"
moved5="$(echo "${result5}" | python3 -c "import json,sys; print(json.load(sys.stdin)['moved'])")"
dry5="$(echo "${result5}" | python3 -c "import json,sys; print(json.load(sys.stdin)['dry_run'])")"
assert_eq "${moved5}" "False" "dry_run_no_move"
assert_eq "${dry5}" "True" "dry_run_flag_true"
# Source file should still exist
assert_eq "$(test -f "${MOCK_INBOX}/dry-run-note.md" && echo "exists" || echo "gone")" "exists" "dry_run_source_preserved"

# --- Test 5: Explicit type override ---
echo "--- Test 5: Explicit type override ---"
cat > "${MOCK_INBOX}/override-note.md" <<'EOF'
---
status: inbox
---
This talks about a decision but we override the type.
EOF

result6="$(bash "${ROOT}/bin/lacp-brain-promote" "${MOCK_INBOX}/override-note.md" --type insight --json 2>/dev/null)"
type6="$(echo "${result6}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type'])")"
auto6="$(echo "${result6}" | python3 -c "import json,sys; print(json.load(sys.stdin)['type_auto_classified'])")"
assert_eq "${type6}" "insight" "explicit_type_override"
assert_eq "${auto6}" "False" "explicit_type_not_auto"

# --- Summary ---
echo ""
echo "[brain-promote] Results: pass=${PASS_COUNT} fail=${FAIL_COUNT}"
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "[brain-promote] SOME TESTS FAILED" >&2
  exit 1
fi
echo "[brain-promote] all brain-promote tests passed"
