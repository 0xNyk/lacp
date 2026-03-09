#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[write-validate] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[write-validate] PASS ${label}"
}

SCRIPT="${ROOT}/hooks/write_validate.py"
VAULT="${TMP}/vault"
mkdir -p "${VAULT}"

export LACP_WRITE_VALIDATE_PATHS="${VAULT}"
export LACP_TAXONOMY_PATH="${TMP}/taxonomy.json"

# Create a minimal taxonomy
cat > "${TMP}/taxonomy.json" <<'JSON'
{
  "version": 1,
  "classification": {
    "category_rules": [
      {"name": "ai-ml-research", "keywords": ["ai"]},
      {"name": "security-governance", "keywords": ["security"]},
      {"name": "general-research", "keywords": ["general"]}
    ]
  }
}
JSON

# --- Test 1: Valid note passes ---
cat > "${VAULT}/good-note.md" <<'MD'
---
title: Test Note
category: ai-ml-research
created: 2026-03-08
tags: [test]
---

# Test Note

Content here.
MD

out="$(python3 "${SCRIPT}" "${VAULT}/good-note.md")"
assert_eq "$(echo "${out}" | jq -r '.status')" "PASS" "valid_note_passes"

# --- Test 2: Missing frontmatter fails ---
cat > "${VAULT}/no-fm.md" <<'MD'
# No Frontmatter

Just content.
MD

out2="$(python3 "${SCRIPT}" "${VAULT}/no-fm.md" || true)"
assert_eq "$(echo "${out2}" | jq -r '.status')" "FAIL" "missing_frontmatter_fails"

# --- Test 3: Missing required field fails ---
cat > "${VAULT}/no-title.md" <<'MD'
---
category: ai-ml-research
created: 2026-03-08
---

Content.
MD

out3="$(python3 "${SCRIPT}" "${VAULT}/no-title.md" || true)"
assert_eq "$(echo "${out3}" | jq -r '.status')" "FAIL" "missing_title_fails"

# --- Test 4: Missing category fails ---
cat > "${VAULT}/no-category.md" <<'MD'
---
title: Test
created: 2026-03-08
---

Content.
MD

out4="$(python3 "${SCRIPT}" "${VAULT}/no-category.md" || true)"
assert_eq "$(echo "${out4}" | jq -r '.status')" "FAIL" "missing_category_fails"

# --- Test 5: Missing recommended fields warns ---
cat > "${VAULT}/no-optional.md" <<'MD'
---
title: Test
category: ai-ml-research
---

Content.
MD

out5="$(python3 "${SCRIPT}" "${VAULT}/no-optional.md")"
assert_eq "$(echo "${out5}" | jq -r '.status')" "WARN" "missing_optional_warns"

# --- Test 6: Unknown category warns ---
cat > "${VAULT}/bad-category.md" <<'MD'
---
title: Test
category: nonexistent-category
created: 2026-03-08
tags: [test]
---

Content.
MD

out6="$(python3 "${SCRIPT}" "${VAULT}/bad-category.md")"
assert_eq "$(echo "${out6}" | jq -r '.status')" "WARN" "unknown_category_warns"

# --- Test 7: Non-markdown file is skipped ---
cat > "${VAULT}/readme.txt" <<'TXT'
Not markdown.
TXT

out7="$(python3 "${SCRIPT}" "${VAULT}/readme.txt")"
assert_eq "$(echo "${out7}" | jq -r '.status')" "SKIP" "non_markdown_skipped"

# --- Test 8: File outside knowledge path is skipped ---
cat > "${TMP}/outside.md" <<'MD'
---
title: Outside
category: ai-ml-research
---

Content.
MD

export LACP_WRITE_VALIDATE_PATHS="${VAULT}"
out8="$(python3 "${SCRIPT}" "${TMP}/outside.md")"
assert_eq "$(echo "${out8}" | jq -r '.status')" "SKIP" "outside_path_skipped"

# --- Test 9: Stdin hook invocation works ---
cat > "${VAULT}/stdin-test.md" <<'MD'
---
title: Stdin Test
category: security-governance
created: 2026-03-08
tags: [hook]
---

Content.
MD

out9="$(echo '{"tool_input":{"file_path":"'"${VAULT}/stdin-test.md"'"}}' | python3 "${SCRIPT}")"
assert_eq "$(echo "${out9}" | jq -r '.status')" "PASS" "stdin_hook_invocation"

# --- Test 10: Exit code is 2 on FAIL ---
set +e
python3 "${SCRIPT}" "${VAULT}/no-fm.md" >/dev/null 2>&1
exit_code=$?
set -e
assert_eq "${exit_code}" "2" "fail_exit_code_is_2"

echo "[write-validate] all write-validate tests passed"
