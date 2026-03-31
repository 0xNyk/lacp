#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$HOME/control/knowledge/knowledge-memory/data/workflows/brain-expand"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/launchd-$(date +%Y-%m-%d).log"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] brain-expand launchd tick"
  /Users/nyk/control/frameworks/lacp/bin/lacp brain-expand --apply --days 7 --json
  echo
} >> "$LOG_FILE" 2>&1
