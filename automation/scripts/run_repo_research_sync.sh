#!/usr/bin/env bash
set -euo pipefail
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="$HOME/control/knowledge/knowledge-memory/data/workflows/repo-research-sync"
mkdir -p "$LOG_DIR"
{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] run-start"
  "$HOME/control/frameworks/lacp/bin/lacp" repo-research-sync --apply --json
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] run-end"
} >> "$LOG_DIR/run-$TS.log" 2>&1
ln -sfn "$LOG_DIR/run-$TS.log" "$LOG_DIR/latest.log"
