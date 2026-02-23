#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
WORKFLOW_DIR=".github/workflows"

fail() {
  echo "[workflow-cost-policy] FAIL $*" >&2
  exit 1
}

allow_action_owner() {
  local owner="$1"
  case "${owner}" in
    actions) return 0 ;;
    *) return 1 ;;
  esac
}

# No active workflows is valid for local-first/no-external-ci repositories.
workflow_count="$(find "${WORKFLOW_DIR}" -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${workflow_count}" == "0" ]]; then
  echo "[workflow-cost-policy] PASS no active workflows under ${WORKFLOW_DIR}"
  exit 0
fi

# Guard 1: only official GitHub actions are allowed in workflows.
while IFS= read -r ref; do
  owner="${ref%%/*}"
  if ! allow_action_owner "${owner}"; then
    fail "third-party action not allowed: ${ref}"
  fi
done < <(rg -n 'uses:\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@' "${WORKFLOW_DIR}"/*.yml "${WORKFLOW_DIR}"/*.yaml 2>/dev/null | sed -E 's/^[^:]+:[0-9]+:.*uses:[[:space:]]*//' )

# Guard 2: no paid external AI/sandbox provider secrets in workflow definitions.
if rg -n 'OPENAI_API_KEY|ANTHROPIC_API_KEY|E2B_API_KEY|DAYTONA_API_KEY|MODAL_TOKEN' "${WORKFLOW_DIR}"/*.yml "${WORKFLOW_DIR}"/*.yaml 2>/dev/null >/dev/null; then
  fail "found disallowed provider secret reference in workflow"
fi

# Guard 3: no direct calls to paid external provider endpoints in workflow scripts.
if rg -n 'api\.openai\.com|api\.anthropic\.com|e2b\.dev|daytona\.io|modal\.com' "${WORKFLOW_DIR}"/*.yml "${WORKFLOW_DIR}"/*.yaml 2>/dev/null >/dev/null; then
  fail "found disallowed external provider endpoint in workflow"
fi

echo "[workflow-cost-policy] PASS workflow definitions satisfy zero-external-cost policy"
