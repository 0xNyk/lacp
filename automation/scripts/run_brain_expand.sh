#!/usr/bin/env bash
set -euo pipefail

: "${LACP_KNOWLEDGE_ROOT:=${HOME}/.lacp/knowledge}"
LOG_DIR="${LACP_BRAIN_EXPAND_LOG_DIR:-${LACP_KNOWLEDGE_ROOT}/data/workflows/brain-expand}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/launchd-$(date +%Y-%m-%d).log"

# Allow overriding the LACP binary location (defaults to PATH resolution).
LACP_BIN="${LACP_BIN:-$(command -v lacp || echo lacp)}"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] brain-expand launchd tick"
  "${LACP_BIN}" brain-expand --apply --days 7 --json
  echo
} >> "$LOG_FILE" 2>&1
