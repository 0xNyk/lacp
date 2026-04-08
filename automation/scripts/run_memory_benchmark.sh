#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TOP_K="${1:-8}"

python3 "${SCRIPT_DIR}/benchmark_memory_retrieval.py" --top-k "${TOP_K}"
