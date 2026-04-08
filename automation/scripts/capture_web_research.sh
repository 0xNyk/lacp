#!/usr/bin/env bash
# capture_web_research.sh — PostToolUse hook for WebSearch|WebFetch
# Appends a single JSONL line to the research-capture spool.
# Designed to be fast (~5ms), safe (mkdir lock), and never block a session (exit 0).
set -uo pipefail

SPOOL_DIR="${HOME}/.local/share/research-capture"
SPOOL_FILE="${SPOOL_DIR}/spool.jsonl"
LOCK_DIR="${SPOOL_FILE}.lock.d"

# Ensure spool directory exists (idempotent)
mkdir -p "${SPOOL_DIR}"

# Read PostToolUse JSON from stdin
INPUT="$(cat)"

# Build a compact JSONL record using jq.
# Truncate tool_response to 50KB to avoid spool bloat.
RECORD="$(echo "${INPUT}" | jq -c '{
  ts: (now | todate),
  session_id: .session_id,
  cwd: .cwd,
  tool_name: .tool_name,
  tool_input: .tool_input,
  tool_response: (.tool_response | tostring | .[0:51200])
}' 2>/dev/null)" || exit 0

# Skip if jq produced nothing (malformed input)
[ -z "${RECORD}" ] && exit 0

# Append with mkdir-based lock for concurrent-write safety (portable macOS/Linux).
# mkdir is atomic — only one process succeeds. Retry briefly, then give up silently.
ATTEMPTS=0
while ! mkdir "${LOCK_DIR}" 2>/dev/null; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "${ATTEMPTS}" -ge 10 ]; then
    # Give up rather than block the session
    exit 0
  fi
  sleep 0.05
done

# Ensure lock is released on exit
trap 'rmdir "${LOCK_DIR}" 2>/dev/null' EXIT

# Rotate spool if over 10MB (matches telemetry rotation: 10MB, 3 backups)
MAX_SPOOL_BYTES=$((10 * 1024 * 1024))
MAX_ROTATIONS=3
if [ -f "${SPOOL_FILE}" ]; then
  SPOOL_SIZE=$(stat -f%z "${SPOOL_FILE}" 2>/dev/null || stat -c%s "${SPOOL_FILE}" 2>/dev/null || echo 0)
  if [ "${SPOOL_SIZE}" -ge "${MAX_SPOOL_BYTES}" ]; then
    for i in $(seq "${MAX_ROTATIONS}" -1 1); do
      src="${SPOOL_FILE}.${i}"
      if [ "${i}" -eq "${MAX_ROTATIONS}" ]; then
        rm -f "${src}"
      else
        dst="${SPOOL_FILE}.$((i + 1))"
        [ -f "${src}" ] && mv "${src}" "${dst}"
      fi
    done
    mv "${SPOOL_FILE}" "${SPOOL_FILE}.1"
  fi
fi

printf '%s\n' "${RECORD}" >> "${SPOOL_FILE}"

exit 0
