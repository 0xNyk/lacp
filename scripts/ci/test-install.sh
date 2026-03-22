#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "[install-test] FAIL ${label}: missing ${path}" >&2
    exit 1
  fi
  echo "[install-test] PASS ${label}: ${path}"
}

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
DRAFTS_ROOT="${TMP}/drafts"

mkdir -p "${AUTOMATION_ROOT}" "${KNOWLEDGE_ROOT}" "${DRAFTS_ROOT}"

export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${DRAFTS_ROOT}"
export LACP_KNOWLEDGE_GRAPH_ROOT="${KNOWLEDGE_ROOT}"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"

"${ROOT}/bin/lacp-install" --profile starter --with-verify --hours 1 --no-obsidian-setup

assert_file "${AUTOMATION_ROOT}/scripts/run_shared_memory.sh" "stub.run_shared_memory"
assert_file "${AUTOMATION_ROOT}/scripts/run_memory_pipeline.sh" "stub.run_memory_pipeline"
assert_file "${AUTOMATION_ROOT}/scripts/run_memory_benchmark_suite.sh" "stub.run_memory_benchmark_suite"
assert_file "${AUTOMATION_ROOT}/scripts/capture_snapshot.py" "stub.capture_snapshot"
assert_file "${AUTOMATION_ROOT}/scripts/run_session_sync.sh" "stub.run_session_sync"
assert_file "${AUTOMATION_ROOT}/scripts/route_inbox.py" "stub.route_inbox"
assert_file "${AUTOMATION_ROOT}/scripts/archive_inbox.py" "stub.archive_inbox"

first_benchmark="$(python3 - <<'PY' "${KNOWLEDGE_ROOT}"
import pathlib
import sys

root = pathlib.Path(sys.argv[1]) / "data" / "benchmarks"
files = sorted(root.glob("*.json"))
if files:
    print(files[0])
PY
)"
first_snapshot="$(python3 - <<'PY' "${AUTOMATION_ROOT}"
import pathlib
import sys

root = pathlib.Path(sys.argv[1]) / "data" / "snapshots"
files = sorted(root.glob("snapshot-*.json"))
if files:
    print(files[0])
PY
)"
assert_file "${first_benchmark}" "artifact.benchmark"
assert_file "${first_snapshot}" "artifact.snapshot"

"${ROOT}/bin/lacp-bootstrap" >/dev/null
"${ROOT}/bin/lacp-verify" --hours 1 >/dev/null
"${ROOT}/bin/lacp-doctor" --json | jq -e '.ok == true' >/dev/null

echo "[install-test] install workflow tests passed"
