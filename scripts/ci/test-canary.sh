#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_SKIP_DOTENV=1
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}/data/benchmarks" "${LACP_DRAFTS_ROOT}"

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
    name = f"benchmark-{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    (root / name).write_text(json.dumps(payload))
PY

pass_json="$("${ROOT}/bin/lacp-canary" --json)"
if [[ "$(echo "${pass_json}" | jq -r '.ok')" != "true" ]]; then
  echo "[canary-test] FAIL expected healthy canary gate" >&2
  exit 1
fi

python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import json
import pathlib
import sys

paths = sorted(pathlib.Path(sys.argv[1]).glob("benchmark-*.json"))
latest = paths[-1]
payload = json.loads(latest.read_text())
payload["summary"]["hit_rate_at_k"] = 0.50
payload["gate_ok"] = False
payload["triage"]["issue_count"] = 5
latest.write_text(json.dumps(payload))
PY

set +e
"${ROOT}/bin/lacp-canary" --days 7 >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[canary-test] FAIL expected unhealthy canary gate to fail" >&2
  exit 1
fi

echo "[canary-test] canary gate tests passed"
