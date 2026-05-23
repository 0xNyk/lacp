#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${LACP_KNOWLEDGE_ROOT:=${HOME}/.lacp/knowledge}"
SESSION_HISTORY_DIR="${LACP_SESSION_HISTORY_DIR:-${LACP_KNOWLEDGE_ROOT}/session-history}"
SESSIONS_RAW_DIR="${LACP_SESSIONS_RAW_DIR:-${LACP_KNOWLEDGE_ROOT}/sessions/raw}"
SYNC_LOG="${SESSION_HISTORY_DIR}/sync.log"

mkdir -p "${SESSION_HISTORY_DIR}" "${SESSIONS_RAW_DIR}"

{
  python3 "${SCRIPT_DIR}/sync_agent_session_history.py" --tail-lines 5000 --manifest-limit 200

  # Extract structured session notes for Obsidian vault
  python3 "${SCRIPT_DIR}/extract_sessions.py" --agent claude --since-days 7
  python3 "${SCRIPT_DIR}/extract_sessions.py" --agent codex --since-days 7

  # Render autogen skill index for Obsidian vault
  python3 "${SCRIPT_DIR}/render_skill_index.py"

  # Render MCP memory entities
  python3 "${SCRIPT_DIR}/render_mcp_memory.py"

  # Re-index QMD collections (picks up new/changed files)
  npx -y @tobilu/qmd update
} >> "${SYNC_LOG}" 2>&1
