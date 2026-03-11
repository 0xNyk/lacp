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

RUNS_DIR="${LACP_KNOWLEDGE_ROOT}/data/sandbox-runs"
mkdir -p "${RUNS_DIR}"

write_case_runs() {
  local scenario="$1"
  rm -f "${RUNS_DIR}"/run-*.json
  python3 - "${RUNS_DIR}" "${scenario}" <<'PY'
import datetime as dt
import json
import pathlib
import sys

runs_dir = pathlib.Path(sys.argv[1])
scenario = sys.argv[2]
now = dt.datetime.now(dt.timezone.utc)

cases = {
    "zero_runs": [],
    "zero_interventions": [
        (1, 0, True),
        (2, 1, True),
    ],
    "normal": [
        (1, 8, False),
        (2, 10, False),
        (3, 0, True),
        (4, 1, True),
    ],
    "baseline_compare": [
        (1, 8, False),
        (2, 10, False),
        (3, 0, True),
        (4, 1, True),
        (25, 8, False),
        (26, 0, True),
        (27, 1, True),
        (28, 0, True),
    ],
}

for idx, (hours_ago, exit_code, executed) in enumerate(cases[scenario], start=1):
    started = (now - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "started_at_utc": started,
        "executed": executed,
        "exit_code": exit_code,
        "task": f"case:{scenario}",
        "command": [],
    }
    (runs_dir / f"run-{scenario}-{idx}.json").write_text(json.dumps(payload))
PY
}

# zero runs
write_case_runs "zero_runs"
zero_json="$("${ROOT}/bin/lacp-report" --hours 24 --baseline-hours 24 --baseline-offset-hours 24 --json)"
echo "${zero_json}" | jq -e '.runs.total == 0' >/dev/null
echo "${zero_json}" | jq -e '.runs.intervened_runs == 0' >/dev/null
echo "${zero_json}" | jq -e '.runs.intervention_rate_per_100 == 0' >/dev/null
echo "${zero_json}" | jq -e '.intervention_rate.delta.percent == null' >/dev/null

# zero interventions
write_case_runs "zero_interventions"
zero_int_json="$("${ROOT}/bin/lacp-report" --hours 24 --baseline-hours 24 --baseline-offset-hours 24 --json)"
echo "${zero_int_json}" | jq -e '.runs.total == 2' >/dev/null
echo "${zero_int_json}" | jq -e '.runs.intervened_runs == 0' >/dev/null
echo "${zero_int_json}" | jq -e '.runs.intervention_rate_per_100 == 0' >/dev/null

# normal case
write_case_runs "normal"
normal_json="$("${ROOT}/bin/lacp-report" --hours 24 --baseline-hours 24 --baseline-offset-hours 24 --json)"
echo "${normal_json}" | jq -e '.runs.total == 4' >/dev/null
echo "${normal_json}" | jq -e '.runs.intervened_runs == 2' >/dev/null
echo "${normal_json}" | jq -e '.runs.intervention_rate_per_100 == 50' >/dev/null

# baseline compare case
write_case_runs "baseline_compare"
baseline_json="$("${ROOT}/bin/lacp-report" --hours 24 --baseline-hours 24 --baseline-offset-hours 24 --json)"
echo "${baseline_json}" | jq -e '.intervention_rate.current_window.total_runs == 4' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.current_window.intervened_runs == 2' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.current_window.intervention_rate_per_100 == 50' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.baseline_window.total_runs == 4' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.baseline_window.intervened_runs == 1' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.baseline_window.intervention_rate_per_100 == 25' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.delta.absolute == 25' >/dev/null
echo "${baseline_json}" | jq -e '.intervention_rate.delta.percent == 100' >/dev/null

echo "[report-intervention-test] intervention rate tests passed"
