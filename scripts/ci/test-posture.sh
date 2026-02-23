#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ok_json="$("${ROOT}/bin/lacp-posture" --json)"
[[ "$(echo "${ok_json}" | jq -r '.ok')" == "true" ]] || { echo "[posture-test] FAIL expected posture ok=true" >&2; exit 1; }
[[ "$(echo "${ok_json}" | jq -r '.checks.local_first.ok')" == "true" ]] || { echo "[posture-test] FAIL expected local_first check pass" >&2; exit 1; }
[[ "$(echo "${ok_json}" | jq -r '.checks.no_external_ci.ok')" == "true" ]] || { echo "[posture-test] FAIL expected no_external_ci check pass" >&2; exit 1; }

set +e
LACP_SKIP_DOTENV=1 LACP_LOCAL_FIRST=false "${ROOT}/bin/lacp-posture" --strict --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[posture-test] FAIL expected strict posture to fail when LACP_LOCAL_FIRST=false" >&2
  exit 1
fi

set +e
LACP_SKIP_DOTENV=1 LACP_NO_EXTERNAL_CI=false "${ROOT}/bin/lacp-posture" --strict --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[posture-test] FAIL expected strict posture to fail when LACP_NO_EXTERNAL_CI=false" >&2
  exit 1
fi

echo "[posture-test] posture tests passed"
