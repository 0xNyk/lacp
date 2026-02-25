#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

REPO="${TMP}/repo"
mkdir -p "${REPO}/docs" "${REPO}/dist"
printf '# Test Repo\n' > "${REPO}/README.md"
printf 'Runbook\n' > "${REPO}/docs/runbook.md"
printf 'Checklist\n' > "${REPO}/docs/release-checklist.md"
printf 'MIT\n' > "${REPO}/LICENSE"
printf 'artifact\n' > "${REPO}/dist/lacp-0.0.0.tar.gz"
(
  cd "${REPO}/dist"
  shasum -a 256 lacp-0.0.0.tar.gz > SHA256SUMS
)

json="$(${ROOT}/bin/lacp-open-source-check --repo-root "${REPO}" --artifacts-dir "${REPO}/dist" --skip-bootstrap --json)"
echo "${json}" | jq -e '.ok == true' >/dev/null
echo "${json}" | jq -e '.summary.fail == 0' >/dev/null
echo "${json}" | jq -e '.checks[] | select(.name=="docs:required_files") | .status == "PASS"' >/dev/null
echo "${json}" | jq -e '.checks[] | select(.name=="release:artifacts") | .status == "PASS"' >/dev/null

echo "[open-source-check-test] open source check tests passed"
