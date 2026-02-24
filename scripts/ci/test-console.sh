#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}/.lacp/commands"

WORK="${TMP}/repo"
mkdir -p "${WORK}/.lacp/commands"

cat > "${HOME}/.lacp/commands/hello.md" <<'EOF'
run: /bin/echo home-hello {{args}}
EOF

cat > "${WORK}/.lacp/commands/hello.md" <<'EOF'
run: /bin/echo project-hello {{args}}
EOF

cat > "${WORK}/.lacp/commands/smoke.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "project-smoke $*"
EOF
chmod +x "${WORK}/.lacp/commands/smoke.sh"

help_out="$("${ROOT}/bin/lacp-console" --eval "/help")"
echo "${help_out}" | rg -q "Interactive LACP shell"

cmds_out="$("${ROOT}/bin/lacp-console" --project-commands-dir "${WORK}/.lacp/commands" --eval "/commands")"
echo "${cmds_out}" | rg -q "^/hello"
echo "${cmds_out}" | rg -q "^/smoke"

hello_out="$("${ROOT}/bin/lacp-console" --project-commands-dir "${WORK}/.lacp/commands" --eval "/hello world")"
[[ "${hello_out}" == "project-hello world" ]]

smoke_out="$("${ROOT}/bin/lacp-console" --project-commands-dir "${WORK}/.lacp/commands" --eval "/smoke run now")"
[[ "${smoke_out}" == "project-smoke run now" ]]

posture_out="$("${ROOT}/bin/lacp-console" --eval "/posture --json")"
echo "${posture_out}" | jq -e '.ok == true' >/dev/null

loop_profile_out="$("${ROOT}/bin/lacp-console" --eval "/loop-profile list --json")"
echo "${loop_profile_out}" | jq -e '.ok == true' >/dev/null

credential_profile_out="$("${ROOT}/bin/lacp-console" --eval "/credential-profile list --json")"
echo "${credential_profile_out}" | jq -e '.ok == true' >/dev/null

loop_shortcut_out="$("${ROOT}/bin/lacp-console" --eval "/loop local-fast trusted-local-dev -- /bin/echo console-loop-ok")"
echo "${loop_shortcut_out}" | jq -e '.ok == true' >/dev/null
echo "${loop_shortcut_out}" | jq -e '.options.loop_profile == "local-fast"' >/dev/null
echo "${loop_shortcut_out}" | jq -e '.options.credential_profile == "trusted-local-dev"' >/dev/null

run_out="$("${ROOT}/bin/lacp-console" --eval "/run posture --json")"
echo "${run_out}" | jq -e '.ok == true' >/dev/null

echo "[console-test] console command tests passed"
