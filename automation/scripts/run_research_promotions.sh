#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DAYS="${1:-30}"
MIN_SCORE="${2:-0.80}"
MIN_COUNT="${3:-2}"

LOG_DIR="/Users/nyk/control/knowledge/knowledge-memory/data/research/promotions"
LOG_FILE="/Users/nyk/control/knowledge/knowledge-memory/data/research-promotions.log"
mkdir -p "${LOG_DIR}"

python3 "${SCRIPT_DIR}/suggest_research_promotions.py" \
  --days "${DAYS}" \
  --min-score "${MIN_SCORE}" \
  --min-count "${MIN_COUNT}" \
  >> "${LOG_FILE}" 2>&1

python3 "${SCRIPT_DIR}/suggest_research_promotions.py" \
  --days "${DAYS}" \
  --min-score "${MIN_SCORE}" \
  --min-count "${MIN_COUNT}" \
  --apply --to-memory \
  >> "${LOG_FILE}" 2>&1
