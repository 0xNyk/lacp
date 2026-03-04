#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

HOOK="${ROOT}/hooks/stop_quality_gate.sh"

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[stop-quality-gate-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_empty() {
  local label="$1" actual="$2"
  if [[ -z "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[stop-quality-gate-test] FAIL ${label}: expected empty, got='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

assert_contains() {
  local label="$1" pattern="$2" actual="$3"
  if echo "${actual}" | /usr/bin/grep -q "${pattern}"; then
    pass=$((pass + 1))
  else
    echo "[stop-quality-gate-test] FAIL ${label}: expected pattern '${pattern}' not found in '${actual}'" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: stop_hook_active=true bypasses evaluation ---
out1=$(echo '{"stop_hook_active": true}' | /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "stop_hook_active=true → allow (empty output)" "${out1}"

# --- Test 2: Missing data → allow ---
out2=$(echo '{}' | /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "empty input → allow" "${out2}"

out3=$(echo '{"transcript_path": "/tmp/nonexistent_12345"}' | /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "nonexistent transcript → allow" "${out3}"

out4=$(echo '{"last_assistant_message": ""}' | /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "empty last_assistant_message → allow" "${out4}"

# --- Test 3: Ollama unreachable → graceful fallback (allow) ---
# Point to a port nothing listens on
# Use env -i to ensure no inherited ollama access, then export inside subshell
out5=$(echo '{"stop_hook_active": false, "last_assistant_message": "I did some stuff"}' \
  | LACP_QUALITY_GATE_URL="http://localhost:19999/api/chat" LACP_QUALITY_GATE_TIMEOUT=2 /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "ollama unreachable → allow (graceful fallback)" "${out5}"

# --- Test 4: Transcript fallback parsing ---
# Create a fake transcript JSONL
TRANSCRIPT="${TMP}/transcript.jsonl"
cat > "${TRANSCRIPT}" <<'JSONL'
{"role":"user","message":{"content":[{"type":"text","text":"Fix the bug"}]}}
{"role":"assistant","message":{"content":[{"type":"text","text":"I looked at it but there are too many issues."}]}}
JSONL

# With ollama unreachable, should still exit 0 (allow)
out6=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"${TRANSCRIPT}\"}" \
  | LACP_QUALITY_GATE_URL="http://localhost:19999/api/chat" LACP_QUALITY_GATE_TIMEOUT=2 /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "transcript fallback + ollama unreachable → allow" "${out6}"

# --- Test 5: Ralph loop integration (structural) ---
mkdir -p "${TMP}/.claude"
cat > "${TMP}/.claude/ralph-loop.local.md" <<'EOF'
---
active: true
iteration: 3
max_iterations: 10
completion_promise: "DONE"
---

Build the thing
EOF

# Run from TMP dir so it finds the ralph state file
out7=$(cd "${TMP}" && echo '{"stop_hook_active": false, "last_assistant_message": "stuff"}' \
  | LACP_QUALITY_GATE_URL="http://localhost:19999/api/chat" LACP_QUALITY_GATE_TIMEOUT=2 /bin/bash "${HOOK}" 2>/dev/null) || true
assert_empty "ralph active + ollama unreachable → allow (no crash)" "${out7}"

rm -f "${TMP}/.claude/ralph-loop.local.md"

# --- Test 6: Script is executable ---
[[ -x "${HOOK}" ]] && pass=$((pass + 1)) || { echo "[stop-quality-gate-test] FAIL hook not executable" >&2; fail=$((fail + 1)); }

# --- Test 7: Script has correct shebang ---
head_line=$(head -1 "${HOOK}")
assert_eq "shebang is #!/usr/bin/env bash" "#!/usr/bin/env bash" "${head_line}"

# --- Test 8: Environment overrides work ---
# Verify the script reads LACP_QUALITY_GATE_MODEL (structural check via grep)
/usr/bin/grep -q 'LACP_QUALITY_GATE_MODEL' "${HOOK}" && pass=$((pass + 1)) || { echo "[stop-quality-gate-test] FAIL missing LACP_QUALITY_GATE_MODEL env var support" >&2; fail=$((fail + 1)); }
/usr/bin/grep -q 'LACP_QUALITY_GATE_URL' "${HOOK}" && pass=$((pass + 1)) || { echo "[stop-quality-gate-test] FAIL missing LACP_QUALITY_GATE_URL env var support" >&2; fail=$((fail + 1)); }
/usr/bin/grep -q 'LACP_QUALITY_GATE_TIMEOUT' "${HOOK}" && pass=$((pass + 1)) || { echo "[stop-quality-gate-test] FAIL missing LACP_QUALITY_GATE_TIMEOUT env var support" >&2; fail=$((fail + 1)); }

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[stop-quality-gate-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[stop-quality-gate-test] all ${total} tests passed"
