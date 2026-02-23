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

ok_json="$("/bin/bash" "${ROOT}/bin/lacp-release-prepare" --quick --skip-cache-gate --skip-skill-audit-gate --no-require-managed-wrappers --json)"
[[ "$(echo "${ok_json}" | jq -r '.ok')" == "true" ]] || { echo "[release-prepare-test] FAIL expected healthy release-prepare" >&2; exit 1; }
[[ "$(echo "${ok_json}" | jq -r '.options.auto_optimize_on_fail')" == "false" ]] || { echo "[release-prepare-test] FAIL expected auto_optimize_on_fail=false by default" >&2; exit 1; }
[[ "$(echo "${ok_json}" | jq -r '.stages.optimize.rc')" == "0" ]] || { echo "[release-prepare-test] FAIL expected optimize rc=0 by default" >&2; exit 1; }

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
"/bin/bash" "${ROOT}/bin/lacp-release-prepare" --quick --skip-cache-gate --skip-skill-audit-gate --no-require-managed-wrappers --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[release-prepare-test] FAIL expected unhealthy release-prepare to fail" >&2
  exit 1
fi

baseline_file="${LACP_KNOWLEDGE_ROOT}/data/benchmarks/canary-baseline.json"
"/bin/bash" "${ROOT}/bin/lacp-canary" --set-clean-baseline --baseline-file "${baseline_file}" >/dev/null
python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import datetime as dt
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
ts = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
payload = {
    "generated_at_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "gate_ok": True,
    "summary": {"hit_rate_at_k": 0.96, "mrr_at_k": 0.75},
    "triage": {"issue_count": 0},
}
(root / f"benchmark-{ts.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(json.dumps(payload))
PY
baseline_json="$("/bin/bash" "${ROOT}/bin/lacp-release-prepare" --quick --canary-days 1 --skip-cache-gate --skip-skill-audit-gate --no-require-managed-wrappers --since-clean-baseline --baseline-file "${baseline_file}" --json)"
[[ "$(echo "${baseline_json}" | jq -r '.options.since_clean_baseline')" == "true" ]] || { echo "[release-prepare-test] FAIL expected since_clean_baseline=true" >&2; exit 1; }
[[ "$(echo "${baseline_json}" | jq -r '.stages.canary.result.window.baseline_mode')" == "true" ]] || { echo "[release-prepare-test] FAIL expected canary baseline_mode=true" >&2; exit 1; }

echo "[release-prepare-test] release prepare tests passed"
