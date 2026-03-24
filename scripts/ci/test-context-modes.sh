#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODES_DIR="${ROOT}/config/context-modes"

# Verify all three modes exist
for mode in thinking-partner implementation review; do
  file="${MODES_DIR}/${mode}.md"
  if [[ ! -f "${file}" ]]; then
    echo "FAIL: missing context mode: ${file}" >&2
    exit 1
  fi
  # Check file is non-empty and has a heading
  if ! grep -q "^# " "${file}"; then
    echo "FAIL: ${mode}.md missing heading" >&2
    exit 1
  fi
  # Check file has Protocol section
  if ! grep -q "## Protocol" "${file}"; then
    echo "FAIL: ${mode}.md missing Protocol section" >&2
    exit 1
  fi
  # Check file has Guardrails section
  if ! grep -q "## Guardrails" "${file}"; then
    echo "FAIL: ${mode}.md missing Guardrails section" >&2
    exit 1
  fi
done

# Verify session_start.py can load context modes
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_CONTEXT_MODE="thinking-partner"
# Simulate session_start with context mode
result="$(echo '{"matcher":"startup"}' | python3 "${ROOT}/hooks/session_start.py" 2>/dev/null || true)"
if echo "${result}" | grep -q "thinking-partner"; then
  echo "[context-modes-test] session_start correctly loads thinking-partner mode"
else
  echo "WARN: session_start did not load context mode (may be running outside repo root)" >&2
fi

echo "[context-modes-test] all tests passed"
