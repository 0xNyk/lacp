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

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter >/dev/null

ok_json="$("/bin/bash" "${ROOT}/bin/lacp-loop" --task "trusted dry run" --repo-trust trusted --dry-run --json -- /bin/echo "hello")"
echo "${ok_json}" | jq -e '.kind == "control_loop"' >/dev/null
echo "${ok_json}" | jq -e '.ok == true' >/dev/null
echo "${ok_json}" | jq -e '.stages.execute.rc == 0' >/dev/null

verify_json="$("/bin/bash" "${ROOT}/bin/lacp-loop" --task "trusted with verify" --repo-trust trusted --dry-run --with-verify --verify-hours 1 --json -- /bin/echo "hello-verify")"
echo "${verify_json}" | jq -e '.stages.verify.rc == 0' >/dev/null

set +e
"/bin/bash" "${ROOT}/bin/lacp-loop" --task "missing context contract" --repo-trust trusted --json -- /bin/mkdir -p "${TMP}/ctx-missing" >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[loop-test] FAIL expected mutating command to fail without --context-contract" >&2
  exit 1
fi

echo "[loop-test] loop tests passed"
