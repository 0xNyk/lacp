#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
ENV_FILE="${ROOT}/.env"
ENV_BACKUP="${TMP}/.env.backup"

cleanup() {
  if [[ -f "${ENV_BACKUP}" ]]; then
    cp "${ENV_BACKUP}" "${ENV_FILE}"
  else
    rm -f "${ENV_FILE}"
  fi
  rm -rf "${TMP}"
}
trap cleanup EXIT

if [[ -f "${ENV_FILE}" ]]; then
  cp "${ENV_FILE}" "${ENV_BACKUP}"
fi

# Wrapper sanity checks.
"${ROOT}/bin/lacp" --help >/dev/null
"${ROOT}/bin/lacp" bootstrap-system --help >/dev/null
"${ROOT}/bin/lacp" doctor --help >/dev/null
"${ROOT}/bin/lacp" test --help >/dev/null
"${ROOT}/bin/lacp" incident-drill --help >/dev/null
"${ROOT}/bin/lacp" posture --help >/dev/null
"${ROOT}/bin/lacp" claude-hooks --help >/dev/null
"${ROOT}/bin/lacp" console --help >/dev/null
"${ROOT}/bin/lacp-claude-hooks" optimize --help >/dev/null
"${ROOT}/bin/lacp" cache-audit --help >/dev/null
"${ROOT}/bin/lacp" cache-guard --help >/dev/null
"${ROOT}/bin/lacp" canary --help >/dev/null
"${ROOT}/bin/lacp" canary-optimize --help >/dev/null
"${ROOT}/bin/lacp" loop --help >/dev/null
"${ROOT}/bin/lacp" up --help >/dev/null
"${ROOT}/bin/lacp" context --help >/dev/null
"${ROOT}/bin/lacp" lessons --help >/dev/null
"${ROOT}/bin/lacp" optimize-loop --help >/dev/null
"${ROOT}/bin/lacp" auto-rollback --help >/dev/null
"${ROOT}/bin/lacp" schedule-health --help >/dev/null
"${ROOT}/bin/lacp" policy-pack --help >/dev/null
"${ROOT}/bin/lacp" release-prepare --help >/dev/null
"${ROOT}/bin/lacp" release-publish --help >/dev/null
"${ROOT}/bin/lacp" release-verify --help >/dev/null
"${ROOT}/bin/lacp" vendor-watch --help >/dev/null
"${ROOT}/bin/lacp" automations-tui --help >/dev/null
"${ROOT}/bin/lacp" mcp-profile --help >/dev/null
"${ROOT}/bin/lacp" skill-audit --help >/dev/null
"${ROOT}/bin/lacp" skill-factory --help >/dev/null
"${ROOT}/bin/lacp" adopt-local --help >/dev/null
"${ROOT}/bin/lacp" unadopt-local --help >/dev/null
"${ROOT}/bin/lacp" release-gate --help >/dev/null
"${ROOT}/bin/lacp" pr-preflight --help >/dev/null
"${ROOT}/bin/lacp" harness-validate --help >/dev/null
"${ROOT}/bin/lacp" harness-run --help >/dev/null
"${ROOT}/bin/lacp" e2e --help >/dev/null
"${ROOT}/bin/lacp" api-e2e --help >/dev/null
"${ROOT}/bin/lacp" contract-e2e --help >/dev/null
"${ROOT}/bin/lacp" browser-evidence-validate --help >/dev/null
"${ROOT}/bin/lacp" orchestrate --help >/dev/null
"${ROOT}/bin/lacp" worktree --help >/dev/null
"${ROOT}/bin/lacp" swarm --help >/dev/null
"${ROOT}/bin/lacp" workflow-run --help >/dev/null

# Pin .env to sentinel values and assert isolated runs do not mutate it.
cat > "${ENV_FILE}" <<'EOF'
LACP_AUTOMATION_ROOT="/tmp/lacp-sentinel/automation"
LACP_KNOWLEDGE_ROOT="/tmp/lacp-sentinel/knowledge"
LACP_DRAFTS_ROOT="/tmp/lacp-sentinel/drafts"
LACP_VERIFY_HOURS="24"
LACP_BENCH_TOP_K="8"
LACP_BENCH_LOOKBACK="30"
EOF

before_hash="$(shasum "${ENV_FILE}" | awk '{print $1}')"
"${ROOT}/bin/lacp" test --isolated >/dev/null
after_hash="$(shasum "${ENV_FILE}" | awk '{print $1}')"

if [[ "${before_hash}" != "${after_hash}" ]]; then
  echo "[cli-env-guard] FAIL .env changed during isolated test run" >&2
  exit 1
fi

echo "[cli-env-guard] PASS wrapper commands and isolated .env guard"
