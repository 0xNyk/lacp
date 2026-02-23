#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

repo="${TMP}/repo"
mkdir -p "${repo}"
"${ROOT}/bin/lacp-context" init-template --repo-root "${repo}" >/dev/null

json="$("${ROOT}/bin/lacp-optimize-loop" --repo-root "${repo}" --iterations 1 --days 1 --dry-run --json)"
echo "${json}" | jq -e '.kind == "optimize_loop"' >/dev/null
echo "${json}" | jq -e '.options.dry_run == true' >/dev/null
echo "${json}" | jq -e '.attempts | length >= 1' >/dev/null
echo "${json}" | jq -e '.proposals | length >= 1' >/dev/null

echo "[optimize-loop-test] optimize-loop tests passed"
