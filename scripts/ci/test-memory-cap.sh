#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1

fail() { echo "[memory-cap-test] FAIL: $1" >&2; exit 1; }

# The session_start hook derives the project memory dir from the cwd slug
# (Claude Code convention: cwd with '/' -> '-'). Build a fake HOME with an
# oversized MEMORY.md and assert the hook surfaces a cap warning.
SLUG="$(python3 -c "from pathlib import Path; print(str(Path.cwd()).replace('/', '-'))")"
MEM_DIR="${TMP}/home/.claude/projects/${SLUG}/memory"
mkdir -p "${MEM_DIR}"

run_hook() {
  # SessionStart hooks read a JSON payload on stdin and emit JSON on stdout.
  echo '{"matcher":""}' | HOME="${TMP}/home" python3 "${ROOT}/hooks/session_start.py" 2>/dev/null || true
}

# ---------- 1. over-cap MEMORY.md -> warning surfaces ----------
python3 -c "
from pathlib import Path
Path('${MEM_DIR}/MEMORY.md').write_text('\n'.join(f'line {i}' for i in range(250)))
"
out="$(run_hook)"
echo "${out}" | grep -q "MEMORY.md is 250 lines" || fail "no cap warning for 250-line MEMORY.md"

# ---------- 2. under-cap MEMORY.md -> no warning ----------
python3 -c "
from pathlib import Path
Path('${MEM_DIR}/MEMORY.md').write_text('\n'.join(f'line {i}' for i in range(50)))
"
out="$(run_hook)"
if echo "${out}" | grep -q "MEMORY.md is"; then
  fail "cap warning fired for a 50-line MEMORY.md"
fi

# ---------- 3. configurable cap via env ----------
out="$(echo '{"matcher":""}' | HOME="${TMP}/home" LACP_MEMORY_MD_LINE_CAP=40 \
  python3 "${ROOT}/hooks/session_start.py" 2>/dev/null || true)"
echo "${out}" | grep -q "MEMORY.md is 50 lines (cap 40)" \
  || fail "configurable cap (LACP_MEMORY_MD_LINE_CAP=40) not honored"

# ---------- 4. missing MEMORY.md -> no crash, no warning ----------
rm -f "${MEM_DIR}/MEMORY.md"
out="$(run_hook)"
if echo "${out}" | grep -q "MEMORY.md is"; then
  fail "cap warning fired with no MEMORY.md present"
fi

echo "[memory-cap-test] all memory-cap tests passed"
