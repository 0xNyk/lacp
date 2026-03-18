#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
ENV_FILE="${ROOT}/.env"
ENV_BACKUP="${TMP}/.env.backup"

cleanup() {
  if [[ -f "${ENV_BACKUP}" ]]; then
    cp "${ENV_BACKUP}" "${ENV_FILE}"
  else
    rm -f "${ENV_FILE}"
  fi
  rm -rf "${TMP}"
}
trap cleanup EXIT

if [[ -f "${ENV_FILE}" ]]; then
  cp "${ENV_FILE}" "${ENV_BACKUP}"
fi

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_WRAPPER_BIN_DIR="${TMP}/bin"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}/data/benchmarks" "${LACP_DRAFTS_ROOT}" "${LACP_WRAPPER_BIN_DIR}"

cat > "${ENV_FILE}" <<EOF
LACP_ALLOW_EXTERNAL_REMOTE="true"
LACP_AUTOMATION_ROOT="${LACP_AUTOMATION_ROOT}"
LACP_KNOWLEDGE_ROOT="${LACP_KNOWLEDGE_ROOT}"
LACP_DRAFTS_ROOT="${LACP_DRAFTS_ROOT}"
EOF

cat > "${LACP_WRAPPER_BIN_DIR}/claude.native" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${LACP_WRAPPER_BIN_DIR}/codex.native" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${LACP_WRAPPER_BIN_DIR}/hermes.native" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "${LACP_WRAPPER_BIN_DIR}/claude.native" "${LACP_WRAPPER_BIN_DIR}/codex.native" "${LACP_WRAPPER_BIN_DIR}/hermes.native"

"/bin/bash" "${ROOT}/bin/lacp-adopt-local" \
  --bin-dir "${LACP_WRAPPER_BIN_DIR}" \
  --claude-native "${LACP_WRAPPER_BIN_DIR}/claude.native" \
  --codex-native "${LACP_WRAPPER_BIN_DIR}/codex.native" \
  --hermes-native "${LACP_WRAPPER_BIN_DIR}/hermes.native" >/dev/null

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
        "gate_ok": False,
        "summary": {"hit_rate_at_k": 0.2, "mrr_at_k": 0.2},
        "triage": {"issue_count": 2},
    }
    name = f"benchmark-{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    (root / name).write_text(json.dumps(payload))
PY

set +e
rollback_json="$("/bin/bash" "${ROOT}/bin/lacp-auto-rollback" --bin-dir "${LACP_WRAPPER_BIN_DIR}" --json)"
rollback_rc=$?
set -e
if [[ "${rollback_rc}" -eq 0 ]]; then
  echo "[auto-rollback-test] FAIL expected non-zero exit when canary is unhealthy" >&2
  exit 1
fi

[[ "$(echo "${rollback_json}" | jq -r '.rollback_applied')" == "true" ]] || { echo "[auto-rollback-test] FAIL rollback_applied=false" >&2; exit 1; }
[[ "$(echo "${rollback_json}" | jq -r '.mode_result.mode')" == "local-only" ]] || { echo "[auto-rollback-test] FAIL mode not local-only" >&2; exit 1; }
[[ -x "${LACP_WRAPPER_BIN_DIR}/claude" ]] || { echo "[auto-rollback-test] FAIL claude command missing" >&2; exit 1; }
[[ -x "${LACP_WRAPPER_BIN_DIR}/codex" ]] || { echo "[auto-rollback-test] FAIL codex command missing" >&2; exit 1; }
[[ -x "${LACP_WRAPPER_BIN_DIR}/hermes" ]] || { echo "[auto-rollback-test] FAIL hermes command missing" >&2; exit 1; }
if rg -q 'LACP_MANAGED_WRAPPER=1' "${LACP_WRAPPER_BIN_DIR}/claude"; then
  echo "[auto-rollback-test] FAIL claude still managed wrapper" >&2
  exit 1
fi
if rg -q 'LACP_MANAGED_WRAPPER=1' "${LACP_WRAPPER_BIN_DIR}/codex"; then
  echo "[auto-rollback-test] FAIL codex still managed wrapper" >&2
  exit 1
fi
if rg -q 'LACP_MANAGED_WRAPPER=1' "${LACP_WRAPPER_BIN_DIR}/hermes"; then
  echo "[auto-rollback-test] FAIL hermes still managed wrapper" >&2
  exit 1
fi

echo "[auto-rollback-test] auto rollback tests passed"
