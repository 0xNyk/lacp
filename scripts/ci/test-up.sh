#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/bin" "${TMP}/automation" "${TMP}/knowledge" "${TMP}/drafts"

cat > "${TMP}/bin/dmux" <<'EOT'
#!/usr/bin/env bash
echo "dmux-stub $*" >&2
exit 0
EOT

cat > "${TMP}/bin/tmux" <<'EOT'
#!/usr/bin/env bash
echo "tmux-stub $*" >&2
exit 0
EOT

chmod +x "${TMP}/bin/dmux" "${TMP}/bin/tmux"

export PATH="${TMP}/bin:${PATH}"
export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"

# Dry-run fanout should produce per-instance launch metadata.
dry_json="$("${ROOT}/bin/lacp-up" --session "ci-up" --instances 3 --command "echo hi" --dry-run --json)"
echo "${dry_json}" | jq -e '.ok == true' >/dev/null
echo "${dry_json}" | jq -e '.summary.instances == 3' >/dev/null
echo "${dry_json}" | jq -e '.summary.succeeded == 3' >/dev/null
echo "${dry_json}" | jq -e '.launches | length == 3' >/dev/null
echo "${dry_json}" | jq -e '[.launches[].session] | unique | length == 1' >/dev/null

# Non-dry-run should work out-of-the-box for dmux (default templates auto-populated in lacp-up).
live_json="$("${ROOT}/bin/lacp-up" --session "ci-up-live" --instances 2 --command "echo hi live" --attach false --json)"
echo "${live_json}" | jq -e '.ok == true' >/dev/null
echo "${live_json}" | jq -e '.summary.succeeded == 2' >/dev/null
echo "${live_json}" | jq -e '.summary.failed == 0' >/dev/null

# tmux backend should use distinct per-instance session names.
tmux_json="$("${ROOT}/bin/lacp-up" --backend tmux --session "ci-up-tmux" --instances 2 --command "echo hi tmux" --dry-run --json)"
echo "${tmux_json}" | jq -e '.ok == true' >/dev/null
echo "${tmux_json}" | jq -e '.launches[0].session == "ci-up-tmux-1"' >/dev/null
echo "${tmux_json}" | jq -e '.launches[1].session == "ci-up-tmux-2"' >/dev/null

echo "[up-test] up command tests passed"
