#!/usr/bin/env zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOG_DIR="${HOME}/control/knowledge/knowledge-memory/data"
mkdir -p "$LOG_DIR"

echo "[$(date -u +%FT%TZ)] X bookmark pipeline starting" >> "$LOG_DIR/x-bookmarks.log"

# Step 1: Fetch bookmarks from jarv via SSH + X API v2 OAuth
BOOKMARKS=$("${SCRIPT_DIR}/fetch_x_bookmarks.sh" --limit 50 2>>"$LOG_DIR/x-bookmarks.log") || {
  echo "[$(date -u +%FT%TZ)] FAIL: fetch_x_bookmarks.sh exited $?" >> "$LOG_DIR/x-bookmarks.log"
  exit 1
}

if [[ -z "$BOOKMARKS" ]]; then
  echo "[$(date -u +%FT%TZ)] No bookmarks fetched (empty response)" >> "$LOG_DIR/x-bookmarks.log"
  exit 0
fi

# Check for API errors
if echo "$BOOKMARKS" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'error' not in d else 1)" 2>/dev/null; then
  # Step 2: Process into inbox notes
  RESULT=$(echo "$BOOKMARKS" | python3 "${SCRIPT_DIR}/process_x_bookmarks.py" --apply 2>>"$LOG_DIR/x-bookmarks.log")
  echo "[$(date -u +%FT%TZ)] Result: $RESULT" >> "$LOG_DIR/x-bookmarks.log"
else
  echo "[$(date -u +%FT%TZ)] FAIL: API returned error: $(echo "$BOOKMARKS" | head -200)" >> "$LOG_DIR/x-bookmarks.log"
  exit 1
fi

echo "[$(date -u +%FT%TZ)] X bookmark pipeline complete" >> "$LOG_DIR/x-bookmarks.log"
