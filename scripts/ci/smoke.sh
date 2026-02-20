#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
DRAFTS_ROOT="${TMP}/drafts"

mkdir -p "${AUTOMATION_ROOT}/scripts" "${KNOWLEDGE_ROOT}" "${DRAFTS_ROOT}"

# Minimal placeholders needed by bootstrap/doctor contracts
for s in run_shared_memory.sh run_memory_pipeline.sh run_memory_benchmark_suite.sh; do
  cat > "${AUTOMATION_ROOT}/scripts/${s}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
  chmod +x "${AUTOMATION_ROOT}/scripts/${s}"
done

cat > "${AUTOMATION_ROOT}/scripts/capture_snapshot.py" <<'EOF'
#!/usr/bin/env python3
print("{}")
EOF
chmod +x "${AUTOMATION_ROOT}/scripts/capture_snapshot.py"

export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${DRAFTS_ROOT}"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"
export LACP_SKIP_DOTENV="1"
export LACP_REMOTE_APPROVAL_FILE="${TMP}/remote-approval.json"

REMOTE_RUNNER="${TMP}/remote-runner.sh"
cat > "${REMOTE_RUNNER}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--" ]]; then
  shift
fi
"$@"
EOF
chmod +x "${REMOTE_RUNNER}"
export LACP_REMOTE_SANDBOX_RUNNER="${REMOTE_RUNNER}"

"${ROOT}/bin/lacp-bootstrap"
"${ROOT}/bin/lacp-route" --task "quant gpu backtest" --cpu-heavy true --long-run true --json >/dev/null
"${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true --dry-run --json >/dev/null
"${ROOT}/bin/lacp-doctor" --json >/dev/null

# Review tier requires TTL approval.
export LACP_ALLOW_EXTERNAL_REMOTE="true"
if "${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true -- /bin/echo "blocked-without-approval"; then
  echo "[smoke] expected remote run to fail without approval" >&2
  exit 1
else
  rc=$?
  if [[ "${rc}" -ne 8 ]]; then
    echo "[smoke] expected exit code 8 for missing/expired approval, got ${rc}" >&2
    exit 1
  fi
fi

python3 - <<'PY' "${LACP_REMOTE_APPROVAL_FILE}"
import datetime as dt
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc)
expires = now + dt.timedelta(minutes=20)
payload = {
    "approved_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "expires_at_utc": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ttl_min": 20,
    "source": "smoke-test",
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload))
PY

"${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true -- /bin/echo "remote-approved-ok" >/dev/null

# Budget gate should block when estimate exceeds tier ceiling without explicit confirmation.
if "${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true --estimated-cost-usd 99 -- /bin/echo "blocked-by-budget"; then
  echo "[smoke] expected run to fail budget gate without --confirm-budget true" >&2
  exit 1
else
  rc=$?
  if [[ "${rc}" -ne 10 ]]; then
    echo "[smoke] expected exit code 10 for budget gate, got ${rc}" >&2
    exit 1
  fi
fi

"${ROOT}/bin/lacp-sandbox-run" --task "remote quant test" --cpu-heavy true --long-run true --estimated-cost-usd 99 --confirm-budget true -- /bin/echo "budget-confirmed-ok" >/dev/null

# Critical tier always requires explicit confirm, regardless of TTL approval.
if "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --cpu-heavy true --long-run true --sensitive-data true -- /bin/echo "blocked-without-critical-confirm"; then
  echo "[smoke] expected critical run to fail without --confirm-critical true" >&2
  exit 1
else
  rc=$?
  if [[ "${rc}" -ne 9 ]]; then
    echo "[smoke] expected exit code 9 for missing critical confirmation, got ${rc}" >&2
    exit 1
  fi
fi

"${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --cpu-heavy true --long-run true --sensitive-data true --confirm-critical true -- /bin/echo "critical-confirmed-ok" >/dev/null
