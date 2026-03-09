#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if echo "${haystack}" | grep -qF "${needle}"; then
    echo "[session-orient] PASS ${label}"
  else
    echo "[session-orient] FAIL ${label}: '${needle}' not found in output" >&2
    echo "--- output ---"
    echo "${haystack}"
    echo "--- end ---"
    exit 1
  fi
}

assert_exit_zero() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "[session-orient] PASS ${label}"
  else
    echo "[session-orient] FAIL ${label}: non-zero exit" >&2
    exit 1
  fi
}

# --- Test 1: Script runs without error even with missing paths ---
export LACP_ROOT="${ROOT}"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"

out="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"

assert_contains "${out}" "LACP Session Orient" "header_present"
assert_contains "${out}" "Recent changes" "recent_changes_section"
assert_contains "${out}" "Last brain-expand" "brain_expand_section"
assert_contains "${out}" "Knowledge structure" "knowledge_structure_section"
assert_contains "${out}" "Active gaps:" "gaps_section"

# --- Test 2: With mock data, shows correct counts ---
mkdir -p "${TMP}/knowledge/data/workflows/brain-expand"
mkdir -p "${TMP}/knowledge/data/gap-detection"
mkdir -p "${TMP}/knowledge/data/review-queue"
mkdir -p "${TMP}/knowledge/graph"
mkdir -p "${TMP}/knowledge/workflows"

cat > "${TMP}/knowledge/data/workflows/brain-expand/launchd-2026-03-08.log" <<'LOG'
[2026-03-08T12:00:00Z] brain-expand launchd tick
{"schema_version":"1","kind":"brain_expand","ok":true,"summary":{"pass":10,"warn":2,"fail":0}}
LOG

cat > "${TMP}/knowledge/data/gap-detection/gaps.json" <<'JSON'
{"gaps": [{"category": "test1"}, {"category": "test2"}, {"category": "test3"}]}
JSON

cat > "${TMP}/knowledge/data/review-queue/review-queue.md" <<'MD'
# Review Queue
- [ ] item-a (retrievability: 0.31)
- [ ] item-b (retrievability: 0.22)
- [ ] item-c (retrievability: 0.15)
- [ ] item-d (retrievability: 0.10)
- [ ] item-e (retrievability: 0.05)
- [ ] item-f (retrievability: 0.03)
- [ ] item-g (retrievability: 0.01)
MD

out2="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"

assert_contains "${out2}" "2026-03-08 PASS (10 pass, 2 warn, 0 fail)" "brain_expand_status"
assert_contains "${out2}" "Active gaps: 3" "gap_count"
assert_contains "${out2}" "Review queue: 7 items" "review_queue_count"

# --- Test 3: With failed brain-expand log ---
cat > "${TMP}/knowledge/data/workflows/brain-expand/launchd-2026-03-08.log" <<'LOG'
[2026-03-08T12:00:00Z] brain-expand launchd tick
{"schema_version":"1","kind":"brain_expand","ok":false,"summary":{"pass":5,"warn":3,"fail":2}}
LOG

out3="$(bash "${ROOT}/hooks/session_orient.sh" 2>&1)"

assert_contains "${out3}" "FAIL (5 pass, 3 warn, 2 fail)" "brain_expand_fail_status"

echo "[session-orient] all session-orient tests passed"
