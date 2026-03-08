#!/usr/bin/env bash
set -euo pipefail

# SessionStart Orientation Hook
# Provides spatial awareness at session start: recent changes, knowledge structure,
# brain-expand status, and active gaps.
#
# Output is kept compact (~20 lines) to avoid context bloat.
# Falls back gracefully if paths don't exist (new installs).

LACP_ROOT="${LACP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
KNOWLEDGE_ROOT="${LACP_KNOWLEDGE_ROOT:-$HOME/control/knowledge/knowledge-memory}"
BRAIN_EXPAND_LOGS="${KNOWLEDGE_ROOT}/data/workflows/brain-expand"
GAP_DETECTION_DIR="${KNOWLEDGE_ROOT}/data/gap-detection"
REVIEW_QUEUE_DIR="${KNOWLEDGE_ROOT}/data/review-queue"

echo "── LACP Session Orient ──────────────────────────"

# Recent LACP repo changes
if [[ -d "${LACP_ROOT}/.git" ]]; then
  echo "Recent changes (lacp):"
  git -C "${LACP_ROOT}" log --oneline -5 2>/dev/null | sed 's/^/  /'
else
  echo "Recent changes: (not a git repo)"
fi

echo ""

# Last brain-expand run status
if [[ -d "${BRAIN_EXPAND_LOGS}" ]]; then
  latest_log=""
  for f in "${BRAIN_EXPAND_LOGS}"/launchd-*.log; do
    [[ -f "${f}" ]] && latest_log="${f}"
  done
  if [[ -n "${latest_log}" ]]; then
    # Extract the last JSON object from the log (may be single-line or multi-line)
    parsed="$(python3 -c "
import json, sys
content = open(sys.argv[1]).read()
# Walk backwards through lines to find JSON objects
data = None
lines = content.rstrip().split('\n')
i = len(lines) - 1
while i >= 0:
    line = lines[i].strip()
    if line == '}' or (line.startswith('{') and line.endswith('}')):
        # Try single-line first
        if line.startswith('{'):
            try:
                data = json.loads(line)
                break
            except Exception:
                pass
        # Multi-line: find matching opening brace
        depth = 0
        for j in range(i, -1, -1):
            depth += lines[j].count('}') - lines[j].count('{')
            if depth <= 0:
                try:
                    data = json.loads('\n'.join(lines[j:i+1]))
                except Exception:
                    data = None
                break
        if data:
            break
    i -= 1
if not data or 'summary' not in data:
    sys.exit(1)
ok = data.get('ok', False)
s = data.get('summary', {})
print(f\"{'PASS' if ok else 'FAIL'} {s.get('pass',0)} {s.get('warn',0)} {s.get('fail',0)}\")
" "${latest_log}" 2>/dev/null || echo "")"
    log_date="$(basename "${latest_log}" | sed 's/launchd-//;s/\.log//')"
    if [[ -n "${parsed}" ]]; then
      read -r status pass warn fail <<< "${parsed}"
      echo "Last brain-expand: ${log_date} ${status} (${pass} pass, ${warn} warn, ${fail} fail)"
    else
      echo "Last brain-expand: ${log_date} (no parseable run in log)"
    fi
  else
    echo "Last brain-expand: (no logs found)"
  fi
else
  echo "Last brain-expand: (log dir missing)"
fi

echo ""

# Knowledge structure (depth 2)
echo "Knowledge structure:"
if [[ -d "${KNOWLEDGE_ROOT}" ]]; then
  # Use find to build a simple tree (portable, no tree command needed)
  (cd "${KNOWLEDGE_ROOT}" && find . -maxdepth 2 -type d | sort | sed 's|^\./||;s|[^/]*/|  |g;/^$/d' | head -15)
else
  echo "  (knowledge root not found)"
fi

echo ""

# Active gaps and review queue counts
gap_count=0
review_count=0

if [[ -f "${GAP_DETECTION_DIR}/gaps.json" ]]; then
  gap_count="$(jq -r '.gaps | length' "${GAP_DETECTION_DIR}/gaps.json" 2>/dev/null || echo 0)"
fi

if [[ -f "${REVIEW_QUEUE_DIR}/review-queue.md" ]]; then
  review_count="$(grep -c '^\- \[' "${REVIEW_QUEUE_DIR}/review-queue.md" 2>/dev/null || echo 0)"
fi

echo "Active gaps: ${gap_count} | Review queue: ${review_count} items"
echo "─────────────────────────────────────────────────"
