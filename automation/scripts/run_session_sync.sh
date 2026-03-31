#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p /Users/nyk/control/session-history /Users/nyk/control/sessions/raw
python3 "${SCRIPT_DIR}/sync_agent_session_history.py" --tail-lines 5000 --manifest-limit 200 \
  >> /Users/nyk/control/session-history/sync.log 2>&1

# Extract structured session notes for Obsidian vault
python3 "${SCRIPT_DIR}/extract_sessions.py" --agent claude --since-days 7 \
  >> /Users/nyk/control/session-history/sync.log 2>&1
python3 "${SCRIPT_DIR}/extract_sessions.py" --agent codex --since-days 7 \
  >> /Users/nyk/control/session-history/sync.log 2>&1

# Render autogen skill index for Obsidian vault
python3 "${SCRIPT_DIR}/render_skill_index.py" \
  >> /Users/nyk/control/session-history/sync.log 2>&1

# Render MCP memory entities
python3 "${SCRIPT_DIR}/render_mcp_memory.py" \
  >> /Users/nyk/control/session-history/sync.log 2>&1

# Re-index QMD collections (picks up new/changed files)
npx -y @tobilu/qmd update \
  >> /Users/nyk/control/session-history/sync.log 2>&1
