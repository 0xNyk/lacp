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
    echo "[brain-expand] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[brain-expand] PASS ${label}"
}

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
SCRIPTS_DIR="${AUTOMATION_ROOT}/scripts"

mkdir -p "${SCRIPTS_DIR}" "${KNOWLEDGE_ROOT}/data/workflows/brain-expand"

export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_KNOWLEDGE_GRAPH_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_DRAFTS_ROOT}"

# --- Test 1: Missing scripts produce WARN, not FAIL ---
# Run brain-expand with no mock scripts at all. Steps 7.5 and 7.6 should WARN.
out="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd 2>/dev/null)"

assert_eq \
  "$(echo "${out}" | jq -r '.steps[] | select(.name=="detect_knowledge_gaps") | .status')" \
  "WARN" \
  "missing_gap_detection_warns"

assert_eq \
  "$(echo "${out}" | jq -r '.steps[] | select(.name=="review_queue") | .status')" \
  "WARN" \
  "missing_review_queue_warns"

assert_eq \
  "$(echo "${out}" | jq -r '.ok')" \
  "true" \
  "missing_scripts_still_ok"

# --- Test 2: Mock gap detection script produces PASS ---
cat > "${SCRIPTS_DIR}/detect_knowledge_gaps.py" <<'MOCK'
#!/usr/bin/env python3
import json, sys, os
# Write a gap-detection note to prove the script ran
knowledge_root = os.environ.get("LACP_KNOWLEDGE_ROOT", "/tmp")
note_dir = os.path.join(knowledge_root, "data", "gap-detection")
os.makedirs(note_dir, exist_ok=True)
with open(os.path.join(note_dir, "gaps.json"), "w") as f:
    json.dump({"gaps": [{"category": "test", "score": 0.42}]}, f)
print(json.dumps({"ok": True, "gaps_found": 1}))
MOCK

out2="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd 2>/dev/null)"

assert_eq \
  "$(echo "${out2}" | jq -r '.steps[] | select(.name=="detect_knowledge_gaps") | .status')" \
  "PASS" \
  "gap_detection_pass"

# Verify the mock actually wrote its output
assert_eq \
  "$(jq -r '.gaps[0].category' "${KNOWLEDGE_ROOT}/data/gap-detection/gaps.json")" \
  "test" \
  "gap_detection_wrote_note"

# --- Test 3: Mock review queue script produces PASS ---
cat > "${SCRIPTS_DIR}/generate_review_queue.py" <<'MOCK'
#!/usr/bin/env python3
import json, sys, os
knowledge_root = os.environ.get("LACP_KNOWLEDGE_ROOT", "/tmp")
queue_dir = os.path.join(knowledge_root, "data", "review-queue")
os.makedirs(queue_dir, exist_ok=True)
with open(os.path.join(queue_dir, "review-queue.md"), "w") as f:
    f.write("# Review Queue\n- [ ] test-node (retrievability: 0.31)\n")
print(json.dumps({"ok": True, "items": 1}))
MOCK

out3="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd 2>/dev/null)"

assert_eq \
  "$(echo "${out3}" | jq -r '.steps[] | select(.name=="review_queue") | .status')" \
  "PASS" \
  "review_queue_pass"

assert_eq \
  "$(head -1 "${KNOWLEDGE_ROOT}/data/review-queue/review-queue.md")" \
  "# Review Queue" \
  "review_queue_wrote_note"

# --- Test 4: Failing mock scripts produce WARN (soft step), not FAIL ---
cat > "${SCRIPTS_DIR}/detect_knowledge_gaps.py" <<'MOCK'
#!/usr/bin/env python3
import sys
print("simulated error", file=sys.stderr)
sys.exit(1)
MOCK

cat > "${SCRIPTS_DIR}/generate_review_queue.py" <<'MOCK'
#!/usr/bin/env python3
import sys
sys.exit(1)
MOCK

out4="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd 2>/dev/null)"

assert_eq \
  "$(echo "${out4}" | jq -r '.steps[] | select(.name=="detect_knowledge_gaps") | .status')" \
  "WARN" \
  "failing_gap_detection_warns"

assert_eq \
  "$(echo "${out4}" | jq -r '.steps[] | select(.name=="review_queue") | .status')" \
  "WARN" \
  "failing_review_queue_warns"

assert_eq \
  "$(echo "${out4}" | jq -r '.ok')" \
  "true" \
  "failing_soft_steps_still_ok"

# --- Test 5: Step ordering — 7.5 and 7.6 run after consolidation (7) and before inbox (8) ---
step_names="$(echo "${out3}" | jq -r '[.steps[].name] | join(",")')"

# Extract positions
consolidation_pos=""
gap_pos=""
queue_pos=""
inbox_pos=""
i=0
IFS=',' read -ra STEP_ARR <<< "${step_names}"
for s in "${STEP_ARR[@]}"; do
  case "${s}" in
    consolidate_research) consolidation_pos="${i}" ;;
    detect_knowledge_gaps) gap_pos="${i}" ;;
    review_queue) queue_pos="${i}" ;;
    route_inbox) inbox_pos="${i}" ;;
  esac
  i=$((i + 1))
done

if [[ -n "${consolidation_pos}" && -n "${gap_pos}" && -n "${queue_pos}" && -n "${inbox_pos}" ]]; then
  if [[ "${consolidation_pos}" -lt "${gap_pos}" && "${gap_pos}" -lt "${queue_pos}" && "${queue_pos}" -lt "${inbox_pos}" ]]; then
    echo "[brain-expand] PASS step_ordering: consolidation(${consolidation_pos}) < gap(${gap_pos}) < queue(${queue_pos}) < inbox(${inbox_pos})"
  else
    echo "[brain-expand] FAIL step_ordering: consolidation=${consolidation_pos} gap=${gap_pos} queue=${queue_pos} inbox=${inbox_pos}" >&2
    exit 1
  fi
else
  echo "[brain-expand] FAIL step_ordering: could not find all step positions in: ${step_names}" >&2
  exit 1
fi

echo "[brain-expand] all brain-expand tests passed"
