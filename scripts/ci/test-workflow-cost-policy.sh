#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

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

# Guard 1: only official GitHub actions are allowed in workflows.
while IFS= read -r ref; do
  owner="${ref%%/*}"
  if ! allow_action_owner "${owner}"; then
    fail "third-party action not allowed: ${ref}"
  fi
done < <(rg -n 'uses:\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@' .github/workflows/*.yml | sed -E 's/^[^:]+:[0-9]+:.*uses:[[:space:]]*//' )

# Guard 2: no paid external AI/sandbox provider secrets in workflow definitions.
if rg -n 'OPENAI_API_KEY|ANTHROPIC_API_KEY|E2B_API_KEY|DAYTONA_API_KEY|MODAL_TOKEN' .github/workflows/*.yml >/dev/null; then
  fail "found disallowed provider secret reference in workflow"
fi

# Guard 3: no direct calls to paid external provider endpoints in workflow scripts.
if rg -n 'api\.openai\.com|api\.anthropic\.com|e2b\.dev|daytona\.io|modal\.com' .github/workflows/*.yml >/dev/null; then
  fail "found disallowed external provider endpoint in workflow"
fi

echo "[workflow-cost-policy] PASS workflow definitions satisfy zero-external-cost policy"
