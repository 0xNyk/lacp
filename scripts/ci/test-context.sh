#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

repo="${TMP}/repo"
mkdir -p "${repo}"

"${ROOT}/bin/lacp-context" init-template --repo-root "${repo}" --json | jq -e '.ok == true' >/dev/null
"${ROOT}/bin/lacp-context" audit --repo-root "${repo}" --json | jq -e '.ok == true' >/dev/null
"${ROOT}/bin/lacp-context" minimize --repo-root "${repo}" --json | jq -e '.kind == "context_minimize"' >/dev/null

# Force bloat to trigger fail.
python3 - <<'PY' "${repo}/CLAUDE.md"
import pathlib,sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text() + "\n" + ("x\n" * 300))
PY

set +e
"${ROOT}/bin/lacp-context" audit --repo-root "${repo}" --max-lines 120 --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[context-test] FAIL expected non-zero for bloated context file" >&2
  exit 1
fi

echo "[context-test] context command tests passed"
