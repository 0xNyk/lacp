#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"

echo "== LACP Council Next Steps Demo =="
echo "repo: $ROOT"

echo
printf '1) Safety defaults (shadow mode)\n'
export LACP_LEARNING_ENABLED=1
export LACP_LEARNING_MODE=shadow
echo "LACP_LEARNING_ENABLED=$LACP_LEARNING_ENABLED"
echo "LACP_LEARNING_MODE=$LACP_LEARNING_MODE"

echo
printf '2) Current status snapshot\n'
git rev-parse --short HEAD || true
if [ "${LACP_DEMO_SKIP_STATUS:-1}" = "1" ]; then
  echo "Skipping bin/lacp-status-report (set LACP_DEMO_SKIP_STATUS=0 to run it)."
else
  if command -v jq >/dev/null 2>&1; then
    bin/lacp-status-report --json | jq '.intervention_rate_kpi? // .'
  else
    bin/lacp-status-report --json || true
  fi
fi

echo
printf '3) Replay evaluation (before/after)\n'
if [ -x "bin/lacp-learn-eval" ]; then
  if command -v jq >/dev/null 2>&1; then
    bin/lacp-learn-eval --json | tee /tmp/lacp-learn-eval.json >/dev/null
    jq '{success_delta, retry_delta, intervention_delta, decision}' /tmp/lacp-learn-eval.json
  else
    bin/lacp-learn-eval --json | tee /tmp/lacp-learn-eval.json
  fi
else
  echo "bin/lacp-learn-eval not present yet (expected during staged rollout)."
fi

echo
printf '4) Provenance + rollback proof\n'
if [ -x "bin/lacp-provenance" ]; then
  if command -v jq >/dev/null 2>&1; then
    bin/lacp-provenance verify --json | jq || true
  else
    bin/lacp-provenance verify --json || true
  fi
fi

if [ -x "bin/lacp-learn-rollback" ]; then
  if command -v jq >/dev/null 2>&1; then
    bin/lacp-learn-rollback --last --dry-run --json | jq || true
  else
    bin/lacp-learn-rollback --last --dry-run --json || true
  fi
else
  echo "bin/lacp-learn-rollback not present yet (expected during staged rollout)."
fi

echo
printf '5) Council decision template\n'
cat <<'EOF'
Decision: GO/NO-GO
Why:
- <evidence bullet 1>
- <evidence bullet 2>
- <evidence bullet 3>
Dissent:
- <unresolved risk or disagreement>
Next 72h:
- <task 1>
- <task 2>
- <task 3>
Fallback trigger:
- If uplift <10% after two weekly cycles -> narrow to Learning Packs.
EOF

echo
echo "Demo run complete. See docs/demos/council-next-steps-demo.md"
