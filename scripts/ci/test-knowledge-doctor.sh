#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[knowledge-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[knowledge-test] PASS ${label}: ${actual}"
}

BROKEN="${TMP}/broken"
CLEAN="${TMP}/clean"
mkdir -p "${BROKEN}/notes" "${CLEAN}/notes"

cat > "${BROKEN}/notes/good-note.md" <<'EOF'
---
description: Valid note
---
See [[missing-target]].
EOF

cat > "${BROKEN}/notes/no-frontmatter.md" <<'EOF'
This file has no frontmatter.
EOF

cat > "${BROKEN}/notes/bad-frontmatter.md" <<'EOF'
---
description: [unterminated
---
Body
EOF

cat > "${BROKEN}/notes/no-description.md" <<'EOF'
---
title: missing description
---
Body
EOF

set +e
broken_json="$("${ROOT}/bin/lacp-knowledge-doctor" --root "${BROKEN}" --json)"
broken_rc=$?
set -e
assert_eq "${broken_rc}" "1" "broken.exit_code"
assert_eq "$(echo "${broken_json}" | jq -r '.ok')" "false" "broken.ok"
assert_eq "$(echo "${broken_json}" | jq -r '.summary.fail >= 2')" "true" "broken.fail-count"
assert_eq "$(echo "${broken_json}" | jq -r '.checks[] | select(.name=="unresolved_wikilinks") | .status')" "FAIL" "broken.unresolved_wikilinks"
assert_eq "$(echo "${broken_json}" | jq -r '.checks[] | select(.name=="frontmatter_missing") | .status')" "FAIL" "broken.frontmatter_missing"

cat > "${CLEAN}/notes/a.md" <<'EOF'
---
description: Alpha note
---
Links to [[b]].
EOF

cat > "${CLEAN}/notes/b.md" <<'EOF'
---
description: Beta note
---
Links back to [[a]].
EOF

set +e
clean_json="$("${ROOT}/bin/lacp-knowledge-doctor" --root "${CLEAN}" --json)"
clean_rc=$?
set -e
assert_eq "${clean_rc}" "0" "clean.exit_code"
assert_eq "$(echo "${clean_json}" | jq -r '.ok')" "true" "clean.ok"
assert_eq "$(echo "${clean_json}" | jq -r '.checks[] | select(.name=="unresolved_wikilinks") | .status')" "PASS" "clean.unresolved_wikilinks"
assert_eq "$(echo "${clean_json}" | jq -r '.checks[] | select(.name=="hard_orphans") | .status')" "PASS" "clean.hard_orphans"

echo "[knowledge-test] knowledge doctor tests passed"
