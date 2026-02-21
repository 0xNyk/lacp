#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/automation/scripts" "${TMP}/knowledge/data/sandbox-runs" "${TMP}/drafts" "${TMP}/bin"

# Fake tmux/dmux/claude for deterministic tests.
cat > "${TMP}/bin/tmux" <<'EOF'
#!/usr/bin/env bash
echo "tmux-stub $*" >&2
exit 0
EOF
cat > "${TMP}/bin/dmux" <<'EOF'
#!/usr/bin/env bash
echo "dmux-stub $*" >&2
exit 0
EOF
cat > "${TMP}/bin/claude" <<'EOF'
#!/usr/bin/env bash
echo "claude-stub $*" >&2
exit 0
EOF
chmod +x "${TMP}/bin/tmux" "${TMP}/bin/dmux" "${TMP}/bin/claude"

export PATH="${TMP}/bin:${PATH}"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_ALLOW_EXTERNAL_REMOTE="false"
export LACP_REQUIRE_INPUT_CONTRACT="false"

# Doctor should render both backends.
doctor_json="$("${ROOT}/bin/lacp-orchestrate" doctor --json)"
echo "${doctor_json}" | jq -e '.backends.tmux.available == true' >/dev/null
echo "${doctor_json}" | jq -e '.backends.dmux.available == true' >/dev/null
echo "${doctor_json}" | jq -e '.backends.claude_worktree.available == true' >/dev/null

# tmux dry run through sandbox gate.
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate tmux dry-run" \
  --backend tmux \
  --session "ci-session-tmux" \
  --command "echo hello from tmux" \
  --repo-trust trusted \
  --dry-run \
  --json >/dev/null

# dmux dry run should pass even without template.
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate dmux dry-run" \
  --backend dmux \
  --session "ci-session-dmux" \
  --command "echo hello from dmux" \
  --repo-trust trusted \
  --dry-run \
  --json >/dev/null

# claude_worktree dry run should render command safely.
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate claude worktree dry-run" \
  --backend claude_worktree \
  --session "ci-claude-worktree" \
  --command "summarize PR risk" \
  --repo-trust trusted \
  --claude-tmux true \
  --dry-run \
  --json >/dev/null

# Non-dry-run dmux requires operator template.
set +e
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate dmux live missing template" \
  --backend dmux \
  --session "ci-session-dmux-live" \
  --command "echo hello from dmux live" \
  --repo-trust trusted >/dev/null 2>/dev/null
rc=$?
set -e
if [[ "${rc}" -ne 12 ]]; then
  echo "[orchestrate-test] FAIL expected rc=12 for missing LACP_DMUX_RUN_TEMPLATE, got ${rc}" >&2
  exit 1
fi

# With template, dmux run succeeds.
export LACP_DMUX_RUN_TEMPLATE='dmux run --session "{session}" --command "{command}"'
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate dmux live" \
  --backend dmux \
  --session "ci-session-dmux-live-ok" \
  --command "echo hello from dmux live ok" \
  --repo-trust trusted >/dev/null

# claude_worktree live run with default template should invoke claude stub.
"${ROOT}/bin/lacp-orchestrate" run \
  --task "orchestrate claude worktree live" \
  --backend claude_worktree \
  --session "ci-claude-worktree-live" \
  --command "run migration checks" \
  --repo-trust trusted \
  --claude-tmux false >/dev/null

echo "[orchestrate-test] orchestrate tests passed"
