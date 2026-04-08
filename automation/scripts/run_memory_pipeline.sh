#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

THRESHOLDS_FILE="${HOME}/control/knowledge/knowledge-memory/benchmarks/thresholds.env"
if [[ -f "${THRESHOLDS_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${THRESHOLDS_FILE}"
fi

HOURS="${1:-24}"
PROMOTION_DAYS="${2:-7}"
PROMOTION_MIN_SCORE="${3:-0.90}"
TOP_K="${4:-8}"
MIN_HIT_RATE="${5:-${MEMORY_BENCH_MIN_HIT_RATE:-0.55}}"
MIN_MRR="${6:-${MEMORY_BENCH_MIN_MRR:-0.33}}"
MIN_NDCG="${7:-${MEMORY_BENCH_MIN_NDCG:-0.60}}"
MAX_INDEX_AGE_MINUTES="${8:-${MEMORY_BENCH_MAX_INDEX_AGE_MINUTES:-180}}"
MAX_SOURCE_LAG_MINUTES="${9:-${MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES:-20}}"
MAX_EMBED_LATENCY_MS="${10:-${MEMORY_BENCH_MAX_EMBED_LATENCY_MS:-5000}}"
MIN_EMBED_DIM="${11:-${MEMORY_BENCH_MIN_EMBED_DIM:-256}}"
MAX_INVALID_PATH_RATIO="${12:-${MEMORY_BENCH_MAX_INVALID_PATH_RATIO:-0}}"
MAX_LEGACY_PATH_RATIO="${13:-${MEMORY_BENCH_MAX_LEGACY_PATH_RATIO:-0}}"

echo "[1/5] Extract shared memory (${HOURS}h)..."
"${SCRIPT_DIR}/run_shared_memory.sh" --hours "${HOURS}"

echo "[2/5] Build hybrid index..."
python3 "${SCRIPT_DIR}/build_memory_rag_index.py" \
  --backend hybrid \
  --allow-sparse-fallback \
  --output ~/control/knowledge/knowledge-memory/data/rag/hybrid-index.json

echo "[3/5] Generate memory promotion suggestions..."
python3 "${SCRIPT_DIR}/suggest_memory_promotions.py" \
  --days "${PROMOTION_DAYS}" \
  --min-score "${PROMOTION_MIN_SCORE}"

echo "[4/5] Generate research promotion suggestions..."
python3 "${SCRIPT_DIR}/suggest_research_promotions.py" \
  --days "${PROMOTION_DAYS}" \
  --min-score "${PROMOTION_MIN_SCORE}" \
  --min-count 2

echo "[5/5] Run retrieval benchmark..."
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
  --require-dense-capability
