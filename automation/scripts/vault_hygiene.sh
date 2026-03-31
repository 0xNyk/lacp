#!/bin/bash
# Weekly vault hygiene — run by LaunchAgent every Sunday at 8 AM
# Routes inbox, detects orphans, validates knowledge graph
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/control/knowledge/knowledge-memory/data/hygiene"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/hygiene-$(date +%Y-%m-%d).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "=== Vault Hygiene Start ==="

# 1. Route inbox items
log "Routing inbox..."
python3 "$SCRIPTS_DIR/route_inbox.py" --apply >> "$LOG_FILE" 2>&1 || true

# 2. Archive old inbox items (>30 days)
log "Archiving old inbox..."
python3 "$SCRIPTS_DIR/archive_inbox.py" --days 30 --apply >> "$LOG_FILE" 2>&1 || true

# 3. Sync research to knowledge graph
log "Syncing research to graph..."
python3 "$SCRIPTS_DIR/sync_research_knowledge.py" --days 7 >> "$LOG_FILE" 2>&1 || true

# 4. Run knowledge doctor
log "Running knowledge doctor..."
if command -v lacp >/dev/null 2>&1; then
    lacp knowledge-doctor >> "$LOG_FILE" 2>&1 || true
fi

# 5. Detect knowledge gaps
log "Detecting knowledge gaps..."
python3 "$SCRIPTS_DIR/detect_knowledge_gaps.py" >> "$LOG_FILE" 2>&1 || true

# 6. Run research consolidation
log "Consolidating research clusters..."
python3 "$SCRIPTS_DIR/consolidate_research.py" >> "$LOG_FILE" 2>&1 || true

# 7. Suggest promotions
log "Suggesting promotions..."
python3 "$SCRIPTS_DIR/suggest_research_promotions.py" --days 7 --min-score 0.75 >> "$LOG_FILE" 2>&1 || true

log "=== Vault Hygiene Complete ==="
