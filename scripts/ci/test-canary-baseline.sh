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

python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import datetime as dt
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc)
for i in range(7):
    ts = now - dt.timedelta(hours=i + 1)
    payload = {
        "generated_at_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_ok": False,
        "summary": {"hit_rate_at_k": 0.2, "mrr_at_k": 0.2},
        "triage": {"issue_count": 5},
    }
    (root / f"benchmark-bad-{i}.json").write_text(json.dumps(payload))
PY

set +e
"/bin/bash" "${ROOT}/bin/lacp-canary" >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[canary-baseline-test] FAIL expected bad canary to fail before baseline" >&2
  exit 1
fi

"/bin/bash" "${ROOT}/bin/lacp-canary" --set-clean-baseline >/dev/null

python3 - <<'PY' "${LACP_KNOWLEDGE_ROOT}/data/benchmarks"
import datetime as dt
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
for i in range(7):
    ts = now + dt.timedelta(seconds=i)
    payload = {
        "generated_at_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_ok": True,
        "summary": {"hit_rate_at_k": 0.98, "mrr_at_k": 0.80},
        "triage": {"issue_count": 0},
    }
    (root / f"benchmark-good-{i}.json").write_text(json.dumps(payload))
PY

baseline_json="$("/bin/bash" "${ROOT}/bin/lacp-canary" --since-clean-baseline --json)"
if [[ "$(echo "${baseline_json}" | jq -r '.ok')" != "true" ]]; then
  echo "[canary-baseline-test] FAIL baseline mode should pass with post-baseline healthy benchmarks" >&2
  exit 1
fi
if [[ "$(echo "${baseline_json}" | jq -r '.window.baseline_mode')" != "true" ]]; then
  echo "[canary-baseline-test] FAIL expected baseline_mode=true" >&2
  exit 1
fi

echo "[canary-baseline-test] canary baseline tests passed"
