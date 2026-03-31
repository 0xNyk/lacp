#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOOKBACK="${1:-60}"
LOG_DIR="${HOME}/control/knowledge/knowledge-memory/data"
LOG_FILE="${LOG_DIR}/recalibration.log"

mkdir -p "${LOG_DIR}" "${HOME}/control/knowledge/knowledge-memory/data/benchmarks/recalibration"

python3 "${SCRIPT_DIR}/recalibrate_memory_benchmark_thresholds.py" \
  --limit "${LOOKBACK}" \
  --apply \
  >> "${LOG_FILE}" 2>&1
