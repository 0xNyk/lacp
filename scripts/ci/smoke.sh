#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
DRAFTS_ROOT="${TMP}/drafts"

mkdir -p "${AUTOMATION_ROOT}/scripts" "${KNOWLEDGE_ROOT}" "${DRAFTS_ROOT}"

# Minimal placeholders needed by bootstrap/doctor contracts
for s in run_shared_memory.sh run_memory_pipeline.sh run_memory_benchmark_suite.sh; do
  cat > "${AUTOMATION_ROOT}/scripts/${s}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
  chmod +x "${AUTOMATION_ROOT}/scripts/${s}"
done

cat > "${AUTOMATION_ROOT}/scripts/capture_snapshot.py" <<'EOF'
#!/usr/bin/env python3
print("{}")
EOF
chmod +x "${AUTOMATION_ROOT}/scripts/capture_snapshot.py"

export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${DRAFTS_ROOT}"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"
export LACP_SKIP_DOTENV="1"

"${ROOT}/bin/lacp-bootstrap"
"${ROOT}/bin/lacp-route" --task "quant gpu backtest" --cpu-heavy true --long-run true --json >/dev/null
"${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true --dry-run --json >/dev/null
"${ROOT}/bin/lacp-doctor" --json >/dev/null
