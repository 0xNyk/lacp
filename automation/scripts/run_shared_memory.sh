#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/extract_shared_memory.py"

if [[ $# -eq 0 ]]; then
  python3 "${PY_SCRIPT}" --hours 24
else
  python3 "${PY_SCRIPT}" "$@"
fi

# Keep drafted article knowledge in the shared memory graph so it is included in retrieval.
python3 "${SCRIPT_DIR}/sync_article_memory.py" \
  --quality-gate \
  --quality-report-dir "${HOME}/control/knowledge/knowledge-memory/data/quality"

# Keep research work as structured, deduplicated, categorized nodes in the shared graph.
python3 "${SCRIPT_DIR}/sync_research_knowledge.py" --days 30 --apply

# Mirror LACP sandbox-run activity (Codex/Claude/Hermes) back into Obsidian daily notes.
python3 "${SCRIPT_DIR}/sync_agent_daily_from_runs.py" --day "$(date +%Y-%m-%d)" --apply --json >/dev/null 2>&1 || true

# Keep Obsidian Agent Daily progress as structured graph notes.
python3 "${SCRIPT_DIR}/sync_agent_daily_knowledge.py" --days 30 --apply --json >/dev/null 2>&1 || true

# Materialize pending web research captures into docs/research/inbox/
python3 "${SCRIPT_DIR}/materialize_research_inbox.py" --apply 2>/dev/null || true
