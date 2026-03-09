#!/usr/bin/env bash
set -euo pipefail

# SessionStart Orientation Hook
# Provides spatial awareness at session start: recent changes, knowledge structure,
# brain-expand status, and active gaps.
#
# Output is kept compact (~20 lines) to avoid context bloat.
# Falls back gracefully if paths don't exist (new installs).

LACP_ROOT="${LACP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
KNOWLEDGE_ROOT="${LACP_KNOWLEDGE_ROOT:-$HOME/.lacp/knowledge}"
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

# Skill-aware hints: surface top 3 matching workflows from the ledger
SKILL_LEDGER="${HOME}/.agents/skills/auto-skill-factory/state/workflow_ledger.json"
if [[ -f "${SKILL_LEDGER}" ]]; then
  skill_hints="$(python3 -c "
import json, sys, os

ledger_path = sys.argv[1]
project_dir = os.environ.get('PROJECT_DIR', os.getcwd())
project_name = os.path.basename(project_dir).lower()
git_branch = ''
try:
    import subprocess
    result = subprocess.run(['git', '-C', project_dir, 'rev-parse', '--abbrev-ref', 'HEAD'],
                          capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        git_branch = result.stdout.strip().lower()
except Exception:
    pass

try:
    ledger = json.load(open(ledger_path))
except Exception:
    sys.exit(0)

workflows = ledger.get('workflows', {})
if len(workflows) < 5:
    sys.exit(0)

scored = []
for key, entry in workflows.items():
    if not isinstance(entry, dict):
        continue
    confidence = float(entry.get('confidence', 0.0))
    if confidence < 0.4:
        continue

    # Relevance boost: check if project/branch matches session history
    relevance = 0.0
    purpose = str(entry.get('purpose', '')).lower()
    signature = str(entry.get('signature', '')).lower()
    text = purpose + ' ' + signature

    if project_name and project_name in text:
        relevance += 0.3
    if git_branch:
        for session in entry.get('sessions', []):
            if isinstance(session, dict):
                if session.get('branch', '').lower() == git_branch:
                    relevance += 0.2
                    break
                if session.get('project', '').lower() == project_name:
                    relevance += 0.1
                    break

    count = int(entry.get('count', 0))
    success_count = int(entry.get('success_count', 0))
    success_rate = (success_count / count) if count > 0 else 0.0
    final_score = confidence + relevance

    scored.append({
        'signature': str(entry.get('signature', '')),
        'count': count,
        'success_pct': int(success_rate * 100),
        'score': final_score,
        'confidence': confidence,
    })

scored.sort(key=lambda x: x['score'], reverse=True)
top = scored[:3]
if not top:
    sys.exit(0)

lines = []
for item in top:
    sig = item['signature'][:50]
    lines.append(f'  - \"{sig}\" ({item[\"count\"]} runs, {item[\"success_pct\"]}% success)')

print('Proven workflows:')
for line in lines:
    print(line)
" "${SKILL_LEDGER}" 2>/dev/null || true)"

  if [[ -n "${skill_hints}" ]]; then
    echo ""
    echo "${skill_hints}"
  fi
fi

echo "─────────────────────────────────────────────────"
