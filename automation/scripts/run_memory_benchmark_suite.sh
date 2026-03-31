#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

THRESHOLDS_FILE="/Users/nyk/control/knowledge/knowledge-memory/benchmarks/thresholds.env"
if [[ -f "${THRESHOLDS_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${THRESHOLDS_FILE}"
fi

TOP_K="${1:-8}"
LOOKBACK="${2:-30}"
MIN_HIT_RATE="${3:-${MEMORY_BENCH_MIN_HIT_RATE:-0.55}}"
MIN_MRR="${4:-${MEMORY_BENCH_MIN_MRR:-0.33}}"
MIN_NDCG="${5:-${MEMORY_BENCH_MIN_NDCG:-0.60}}"
MAX_INDEX_AGE_MINUTES="${6:-${MEMORY_BENCH_MAX_INDEX_AGE_MINUTES:-180}}"
MAX_SOURCE_LAG_MINUTES="${7:-${MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES:-20}}"
MAX_EMBED_LATENCY_MS="${8:-${MEMORY_BENCH_MAX_EMBED_LATENCY_MS:-5000}}"
MIN_EMBED_DIM="${9:-${MEMORY_BENCH_MIN_EMBED_DIM:-256}}"
MAX_INVALID_PATH_RATIO="${10:-${MEMORY_BENCH_MAX_INVALID_PATH_RATIO:-0}}"
MAX_LEGACY_PATH_RATIO="${11:-${MEMORY_BENCH_MAX_LEGACY_PATH_RATIO:-0}}"

mkdir -p /Users/nyk/control/knowledge/knowledge-memory/data/benchmarks /Users/nyk/control/knowledge/knowledge-memory/data/benchmarks/trends

set +e
python3 "${SCRIPT_DIR}/benchmark_memory_retrieval.py" \
  --top-k "${TOP_K}" \
  --enforce-gates \
  --min-hit-rate "${MIN_HIT_RATE}" \
  --min-mrr "${MIN_MRR}" \
  --min-ndcg "${MIN_NDCG}" \
  --max-index-age-minutes "${MAX_INDEX_AGE_MINUTES}" \
  --max-source-lag-minutes "${MAX_SOURCE_LAG_MINUTES}" \
  --max-embed-latency-ms "${MAX_EMBED_LATENCY_MS}" \
  --min-embed-dim "${MIN_EMBED_DIM}" \
  --max-invalid-path-ratio "${MAX_INVALID_PATH_RATIO}" \
  --max-legacy-path-ratio "${MAX_LEGACY_PATH_RATIO}" \
  --require-dense-capability \
  >> /Users/nyk/control/knowledge/knowledge-memory/data/benchmark.log 2>&1
BENCH_RC=$?
set -e

python3 "${SCRIPT_DIR}/benchmark_memory_trends.py" --limit "${LOOKBACK}" \
  >> /Users/nyk/control/knowledge/knowledge-memory/data/benchmark.log 2>&1

exit "${BENCH_RC}"
