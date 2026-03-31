#!/usr/bin/env bash
# Test the 5 brain-expand pipeline scripts directly (no brain-expand wrapper).
# Each script is exercised with a real temp directory structure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
passed=0
failed=0

cleanup() { rm -rf "${TMP}"; }
trap cleanup EXIT

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[brain-scripts] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    failed=$((failed + 1))
    return 1
  fi
  echo "[brain-scripts] PASS ${label}"
  passed=$((passed + 1))
}

export LACP_SKIP_DOTENV=1
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_KNOWLEDGE_GRAPH_ROOT="${TMP}/knowledge"
INBOX="${LACP_KNOWLEDGE_ROOT}/inbox"
mkdir -p "${INBOX}" "${LACP_KNOWLEDGE_ROOT}/data"

# ─── Test 1: run_session_sync.sh ───────────────────────────────────────────

# Create a fake Claude project memory dir
FAKE_PROJ="${TMP}/fake-claude-projects/test-project/memory"
mkdir -p "${FAKE_PROJ}"
echo "# Test Memory" > "${FAKE_PROJ}/MEMORY.md"

# Patch HOME so the script scans our fake dir instead of real ~/.claude
export HOME="${TMP}"
mkdir -p "${TMP}/.claude/projects/test-project/memory"
echo "# Test Note" > "${TMP}/.claude/projects/test-project/memory/test.md"

out="$(bash "${ROOT}/scripts/run_session_sync.sh" 2>/dev/null)"
assert_eq "$(echo "${out}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ok"])')" "True" "session_sync:json_output"
assert_eq "$(echo "${out}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["synced"] >= 1)')" "True" "session_sync:synced_count"

# Verify the note landed in inbox with frontmatter
inbox_files=(${INBOX}/session-*.md)
if [[ -f "${inbox_files[0]}" ]]; then
  assert_eq "$(head -1 "${inbox_files[0]}")" "---" "session_sync:frontmatter_present"
else
  echo "[brain-scripts] FAIL session_sync:file_created" >&2
  failed=$((failed + 1))
fi

# ─── Test 2: detect_knowledge_gaps.py ──────────────────────────────────────

# Create some graph notes with wikilinks
GRAPH="${LACP_KNOWLEDGE_ROOT}"
mkdir -p "${GRAPH}/concepts"
cat > "${GRAPH}/concepts/real-note.md" <<'EOF'
---
type: concept
---
Links to [[missing-target]] and [[orphan-note]].
EOF
cat > "${GRAPH}/concepts/orphan-note.md" <<'EOF'
---
type: concept
---
This note has no inbound links besides from real-note.
EOF

out2="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/detect_knowledge_gaps.py" 2>/dev/null)"
assert_eq "$(echo "${out2}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ok"])')" "True" "detect_gaps:ok"
# Should find at least 1 broken link (missing-target)
gaps_found="$(echo "${out2}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["gaps_found"])')"
assert_eq "$([[ "${gaps_found}" -ge 1 ]] && echo yes || echo no)" "yes" "detect_gaps:found_broken_link"

# Verify gaps.json was written
assert_eq "$(test -f "${LACP_KNOWLEDGE_ROOT}/data/gap-detection/gaps.json" && echo yes)" "yes" "detect_gaps:wrote_json"

# ─── Test 3: generate_review_queue.py ──────────────────────────────────────

# Create an old inbox note (touch with old mtime)
cat > "${INBOX}/old-note.md" <<'EOF'
---
type: session-extract
status: pending
tags: ai
---
Old content with [[some-link]].
EOF
touch -t 202501010000 "${INBOX}/old-note.md"

out3="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/generate_review_queue.py" 2>/dev/null)"
assert_eq "$(echo "${out3}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ok"])')" "True" "review_queue:ok"
items="$(echo "${out3}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"])')"
assert_eq "$([[ "${items}" -ge 1 ]] && echo yes || echo no)" "yes" "review_queue:found_old_note"
assert_eq "$(test -f "${LACP_KNOWLEDGE_ROOT}/data/review-queue/review-queue.md" && echo yes)" "yes" "review_queue:wrote_md"

# ─── Test 4: route_inbox.py (dry run) ─────────────────────────────────────

cat > "${INBOX}/route-test.md" <<'EOF'
---
type: session-extract
status: pending
---
Test session content.
EOF

out4="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/route_inbox.py" 2>/dev/null | tail -1)"
assert_eq "$(echo "${out4}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ok"])')" "True" "route_inbox:ok"
routed="$(echo "${out4}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["routed"])')"
assert_eq "$([[ "${routed}" -ge 1 ]] && echo yes || echo no)" "yes" "route_inbox:dry_run_routed"
# File should still be in inbox (dry run)
assert_eq "$(test -f "${INBOX}/route-test.md" && echo yes)" "yes" "route_inbox:dry_run_no_move"

# Test --apply actually moves the file
out4b="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/route_inbox.py" --apply 2>/dev/null)"
assert_eq "$(test -f "${INBOX}/route-test.md" && echo yes || echo no)" "no" "route_inbox:apply_moved"
assert_eq "$(test -f "${GRAPH}/sessions/route-test.md" && echo yes)" "yes" "route_inbox:apply_destination"

# ─── Test 5: archive_inbox.py (dry run + apply) ───────────────────────────

cat > "${INBOX}/archive-test.md" <<'EOF'
---
type: misc
status: pending
---
Old misc content.
EOF
touch -t 202501010000 "${INBOX}/archive-test.md"

out5="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/archive_inbox.py" --days 7 2>/dev/null | tail -1)"
assert_eq "$(echo "${out5}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ok"])')" "True" "archive_inbox:ok"
archived="$(echo "${out5}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["archived"])')"
assert_eq "$([[ "${archived}" -ge 1 ]] && echo yes || echo no)" "yes" "archive_inbox:dry_run_found"
# File should still be in inbox (dry run)
assert_eq "$(test -f "${INBOX}/archive-test.md" && echo yes)" "yes" "archive_inbox:dry_run_no_move"

# Apply
out5b="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/archive_inbox.py" --days 7 --apply 2>/dev/null)"
assert_eq "$(test -f "${INBOX}/archive-test.md" && echo yes || echo no)" "no" "archive_inbox:apply_moved"
assert_eq "$(test -f "${LACP_KNOWLEDGE_ROOT}/archive/inbox/archive-test.md" && echo yes)" "yes" "archive_inbox:apply_destination"

# ─── Test 6: path traversal guard ─────────────────────────────────────────

# Create a file with .. in the name (should be skipped)
touch "${INBOX}/..sneaky..md"
out6="$(PYTHONPATH="${ROOT}/scripts" python3 "${ROOT}/scripts/route_inbox.py" --apply 2>/dev/null)"
# The file should still be in inbox (skipped by guard)
assert_eq "$(test -f "${INBOX}/..sneaky..md" && echo yes)" "yes" "path_traversal:skipped"

# ─── Summary ──────────────────────────────────────────────────────────────

echo ""
echo "Results: ${passed} passed, ${failed} failed"
[[ "${failed}" -eq 0 ]] || exit 1
