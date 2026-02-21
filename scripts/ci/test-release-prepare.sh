#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}/data/benchmarks" "${LACP_DRAFTS_ROOT}"

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter --with-verify --hours 1 >/dev/null

python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import datetime as dt
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc)
for i in range(7):
    ts = now - dt.timedelta(days=i)
    payload = {
        "generated_at_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_ok": True,
        "summary": {"hit_rate_at_k": 0.96, "mrr_at_k": 0.75},
        "triage": {"issue_count": 0},
    }
    (root / f"benchmark-{ts.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(json.dumps(payload))
PY

ok_json="$("/bin/bash" "${ROOT}/bin/lacp-release-prepare" --quick --skip-cache-gate --skip-skill-audit-gate --json)"
[[ "$(echo "${ok_json}" | jq -r '.ok')" == "true" ]] || { echo "[release-prepare-test] FAIL expected healthy release-prepare" >&2; exit 1; }

python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import json
import pathlib
import sys

paths = sorted(pathlib.Path(sys.argv[1]).glob("benchmark-*.json"))
latest = paths[-1]
payload = json.loads(latest.read_text())
payload["gate_ok"] = False
payload["summary"]["hit_rate_at_k"] = 0.1
payload["summary"]["mrr_at_k"] = 0.1
payload["triage"]["issue_count"] = 9
latest.write_text(json.dumps(payload))
PY

set +e
"/bin/bash" "${ROOT}/bin/lacp-release-prepare" --quick --skip-cache-gate --skip-skill-audit-gate --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[release-prepare-test] FAIL expected unhealthy release-prepare to fail" >&2
  exit 1
fi

echo "[release-prepare-test] release prepare tests passed"
