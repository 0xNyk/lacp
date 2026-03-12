#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

CLEAN_REPO="${TMP}/clean"
mkdir -p "${CLEAN_REPO}"
(
  cd "${CLEAN_REPO}"
  git init -q
  cat > README.md <<'EOF'
# clean
EOF
  mkdir -p docs .github/workflows-disabled
  cat > docs/runbook.md <<'EOF'
All good.
EOF
  cat > .github/workflows-disabled/ci.yml <<'EOF'
name: disabled
EOF
  git add README.md docs/runbook.md .github/workflows-disabled/ci.yml
)

clean_json="$(/bin/bash "${ROOT}/scripts/ci/security-hygiene-audit.sh" --repo-root "${CLEAN_REPO}" --json)"
echo "${clean_json}" | jq -e '.ok == true' >/dev/null
echo "${clean_json}" | jq -e '.summary.fail == 0' >/dev/null

DIRTY_REPO="${TMP}/dirty"
mkdir -p "${DIRTY_REPO}"
(
  cd "${DIRTY_REPO}"
  git init -q
  cat > leak.txt <<'EOF'
leak=ghp_ABCDEFGHIJKLMNOPQRST
EOF
  cat > path.txt <<'EOF'
private path /Users/demo/private
EOF
  cat > email.txt <<'EOF'
owner@acme.io
EOF
  cat > .env <<'EOF'
LACP_LOCAL_FIRST=true
EOF
  mkdir -p .github/workflows
  cat > .github/workflows/ci.yml <<'EOF'
name: ci
on: [push]
jobs: {}
EOF
  git add leak.txt path.txt email.txt .env .github/workflows/ci.yml
)

dirty_json="$(/bin/bash "${ROOT}/scripts/ci/security-hygiene-audit.sh" --repo-root "${DIRTY_REPO}" --json || true)"
echo "${dirty_json}" | jq -e '.ok == false' >/dev/null
echo "${dirty_json}" | jq -e '.summary.fail >= 4' >/dev/null
echo "${dirty_json}" | jq -e '.summary.warn >= 1' >/dev/null
echo "${dirty_json}" | jq -e '.checks[] | select(.name=="secrets:high_signal_patterns") | .status == "FAIL"' >/dev/null
echo "${dirty_json}" | jq -e '.checks[] | select(.name=="hygiene:absolute_paths") | .status == "FAIL"' >/dev/null
echo "${dirty_json}" | jq -e '.checks[] | select(.name=="policy:tracked_dotenv") | .status == "FAIL"' >/dev/null
echo "${dirty_json}" | jq -e '.checks[] | select(.name=="policy:active_external_ci_workflows") | .status == "FAIL"' >/dev/null
echo "${dirty_json}" | jq -e '.checks[] | select(.name=="hygiene:email_literals") | .status == "WARN"' >/dev/null

echo "[security-hygiene-audit-test] security hygiene audit tests passed"
