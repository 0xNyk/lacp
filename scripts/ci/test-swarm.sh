#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/automation/scripts" "${TMP}/knowledge/data/sandbox-runs" "${TMP}/drafts" "${TMP}/bin"

cat > "${TMP}/bin/tmux" <<'EOT'
#!/usr/bin/env bash
echo "tmux-stub $*" >&2
exit 0
EOT
cat > "${TMP}/bin/dmux" <<'EOT'
#!/usr/bin/env bash
echo "dmux-stub $*" >&2
exit 0
EOT
cat > "${TMP}/bin/claude" <<'EOT'
#!/usr/bin/env bash
echo "claude-stub $*" >&2
exit 0
EOT
chmod +x "${TMP}/bin/tmux" "${TMP}/bin/dmux" "${TMP}/bin/claude"

export PATH="${TMP}/bin:${PATH}"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_ALLOW_EXTERNAL_REMOTE="false"
export LACP_REQUIRE_INPUT_CONTRACT="false"
export LACP_DMUX_TUI_TEMPLATE='dmux attach --session "{session}"'

manifest="${TMP}/swarm.json"

"${ROOT}/bin/lacp-swarm" init --manifest "${manifest}" --json | jq -e '.ok == true' >/dev/null
"${ROOT}/bin/lacp-swarm" plan --manifest "${manifest}" --json | jq -e '.ok == true and .summary.jobs >= 1' >/dev/null

launch_json="$("${ROOT}/bin/lacp-swarm" launch --manifest "${manifest}" --json)"
echo "${launch_json}" | jq -e '.ok == true and (.artifact | length > 0)' >/dev/null
artifact_path="$(echo "${launch_json}" | jq -r '.artifact')"
[[ -f "${artifact_path}" ]] || { echo "[swarm-test] FAIL missing artifact file" >&2; exit 1; }

"${ROOT}/bin/lacp-swarm" status --file "${artifact_path}" --json | jq -e '.ok == true and .swarm_id != null' >/dev/null
"${ROOT}/bin/lacp-swarm" status --latest --json | jq -e '.ok == true and .swarm_id != null' >/dev/null

up_json="$("${ROOT}/bin/lacp-swarm" up --manifest "${TMP}/swarm-up.json" --json)"
echo "${up_json}" | jq -e '.ok == true and .initialized == true and (.launch.artifact | length > 0)' >/dev/null

"${ROOT}/bin/lacp-swarm" tui --session "swarm-analysis" --dry-run --json | \
  jq -e '.ok == true and .session == "swarm-analysis" and (.command | test("attach --session"))' >/dev/null

"${ROOT}/bin/lacp-swarm" tui --manifest "${manifest}" --dry-run --json | \
  jq -e '.ok == true and .session != null and (.command | test("attach --session"))' >/dev/null

cat > "${TMP}/collision.json" <<'JSON'
{
  "version": "1",
  "name": "collision-test",
  "continue_on_error": false,
  "defaults": {
    "backend": "dmux",
    "repo_trust": "trusted",
    "dry_run": true
  },
  "jobs": [
    {
      "task": "stream a",
      "session": "a",
      "command": "codex --help",
      "reservations": ["src/shared/"]
    },
    {
      "task": "stream b",
      "session": "b",
      "command": "claude --help",
      "reservations": ["src/shared/file.ts"]
    }
  ]
}
JSON

collision_plan="$("${ROOT}/bin/lacp-swarm" plan --manifest "${TMP}/collision.json" --json)"
echo "${collision_plan}" | jq -e '.ok == true' >/dev/null
echo "${collision_plan}" | jq -e '.collaboration.reservations_total == 2' >/dev/null
echo "${collision_plan}" | jq -e '.collaboration.collisions_total >= 1' >/dev/null
echo "${collision_plan}" | jq -e '.warnings | length >= 1' >/dev/null

cat > "${TMP}/bad.json" <<'JSON'
{"version":"1","name":"bad","jobs":[]}
JSON
set +e
"${ROOT}/bin/lacp-swarm" plan --manifest "${TMP}/bad.json" --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[swarm-test] FAIL expected invalid plan rc=1, got ${rc}" >&2
  exit 1
fi

echo "[swarm-test] swarm command tests passed"
