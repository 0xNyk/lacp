#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

CLAUDE_DIR="${TMP}/.claude"
mkdir -p "${CLAUDE_DIR}/plugins/cache/thedotmack/claude-mem"
mkdir -p "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/.claude-plugin"
mkdir -p "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/hooks"
mkdir -p "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/scripts"

cat > "${CLAUDE_DIR}/settings.json" <<'EOF'
{
  "enabledPlugins": {
    "claude-mem@thedotmack": true
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "test"
          }
        ]
      }
    ]
  }
}
EOF

cat > "${CLAUDE_DIR}/plugins/installed_plugins.json" <<'EOF'
{
  "version": 2,
  "plugins": {
    "claude-mem@thedotmack": [
      {
        "scope": "user",
        "installPath": "/tmp/does-not-exist/claude-mem/9.0.0",
        "version": "9.0.0"
      }
    ]
  }
}
EOF

cat > "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "claude-mem",
  "version": "9.0.5"
}
EOF

cat > "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/hooks/hooks.json" <<'EOF'
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bun \"${CLAUDE_PLUGIN_ROOT}/scripts/worker-service.cjs\" start"
          }
        ]
      }
    ]
  }
}
EOF

cat > "${CLAUDE_DIR}/plugins/marketplaces/thedotmack/plugin/scripts/worker-service.cjs" <<'EOF'
#!/usr/bin/env node
console.log("ok");
EOF

audit_before="$("${ROOT}/bin/lacp-claude-hooks" audit --claude-dir "${CLAUDE_DIR}" --json)"
[[ "$(echo "${audit_before}" | jq -r '.summary.missing_plugin_paths')" == "1" ]] || {
  echo "[claude-hooks-test] FAIL expected 1 missing plugin path before repair" >&2
  exit 1
}

repair_json="$("${ROOT}/bin/lacp-claude-hooks" repair --claude-dir "${CLAUDE_DIR}" --json)"
[[ "$(echo "${repair_json}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL repair not ok" >&2
  exit 1
}

expected_install="${CLAUDE_DIR}/plugins/cache/thedotmack/claude-mem/9.0.5"
[[ -d "${expected_install}" ]] || {
  echo "[claude-hooks-test] FAIL expected repaired cache path ${expected_install}" >&2
  exit 1
}

installed_path="$(echo "${repair_json}" | jq -r '.actions[] | select(.action=="update_installed_plugins_entry") | .to_path')"
expected_install_real="$(python3 - <<'PY' "${expected_install}"
import pathlib,sys
print(pathlib.Path(sys.argv[1]).resolve())
PY
)"
installed_path_real="$(python3 - <<'PY' "${installed_path}"
import pathlib,sys
print(pathlib.Path(sys.argv[1]).resolve())
PY
)"
[[ "${installed_path_real}" == "${expected_install_real}" ]] || {
  echo "[claude-hooks-test] FAIL expected installed path ${expected_install}, got ${installed_path}" >&2
  exit 1
}

audit_after="$("${ROOT}/bin/lacp-claude-hooks" audit --claude-dir "${CLAUDE_DIR}" --json)"
[[ "$(echo "${audit_after}" | jq -r '.summary.missing_plugin_paths')" == "0" ]] || {
  echo "[claude-hooks-test] FAIL expected no missing plugin paths after repair" >&2
  exit 1
}

profile_dry="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile minimal-stop --dry-run --json)"
[[ "$(echo "${profile_dry}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL dry-run apply-profile not ok" >&2
  exit 1
}
[[ "$(echo "${profile_dry}" | jq -r '.actions[] | select(.plugin=="claude-mem@thedotmack") | .action' | head -n1)" == "disable_plugin" ]] || {
  echo "[claude-hooks-test] FAIL expected disable_plugin action for claude-mem" >&2
  exit 1
}

profile_apply="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile minimal-stop --json)"
[[ "$(echo "${profile_apply}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL apply-profile not ok" >&2
  exit 1
}
[[ "$(jq -r '.enabledPlugins["claude-mem@thedotmack"]' "${CLAUDE_DIR}/settings.json")" == "false" ]] || {
  echo "[claude-hooks-test] FAIL expected claude-mem disabled in settings" >&2
  exit 1
}

optimize_json="$("${ROOT}/bin/lacp-claude-hooks" optimize --claude-dir "${CLAUDE_DIR}" --profile minimal-stop --json)"
[[ "$(echo "${optimize_json}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL optimize not ok" >&2
  exit 1
}
[[ "$(echo "${optimize_json}" | jq -r '.audit.summary.plugin_stop_hooks')" == "0" ]] || {
  echo "[claude-hooks-test] FAIL expected plugin stop hooks to be 0 after optimize" >&2
  exit 1
}

hardened_json="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile hardened-exec --json)"
[[ "$(echo "${hardened_json}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL hardened-exec apply-profile not ok" >&2
  exit 1
}
[[ -f "${CLAUDE_DIR}/lacp-hooks/exec_guard.py" ]] || {
  echo "[claude-hooks-test] FAIL missing exec_guard.py after hardened-exec apply" >&2
  exit 1
}
[[ -f "${CLAUDE_DIR}/lacp-hooks/config_guard.py" ]] || {
  echo "[claude-hooks-test] FAIL missing config_guard.py after hardened-exec apply" >&2
  exit 1
}
[[ "$(jq -r '.hooks.PreToolUse[-1].hooks[0].command' "${CLAUDE_DIR}/settings.json")" == *"lacp-hooks/exec_guard.py"* ]] || {
  echo "[claude-hooks-test] FAIL expected PreToolUse managed command hook" >&2
  exit 1
}
[[ "$(jq -r '.hooks.PermissionRequest[-1].hooks[0].command' "${CLAUDE_DIR}/settings.json")" == *"lacp-hooks/exec_guard.py"* ]] || {
  echo "[claude-hooks-test] FAIL expected PermissionRequest managed command hook" >&2
  exit 1
}
[[ "$(jq -r '.hooks.ConfigChange[-1].hooks[0].command' "${CLAUDE_DIR}/settings.json")" == *"lacp-hooks/config_guard.py"* ]] || {
  echo "[claude-hooks-test] FAIL expected ConfigChange managed command hook" >&2
  exit 1
}

# --- quality-gate profile ---

# Reset settings for quality-gate test
cat > "${CLAUDE_DIR}/settings.json" <<'EOF'
{
  "enabledPlugins": {},
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Review the assistant response..."
          }
        ]
      }
    ]
  }
}
EOF

qg_dry="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile quality-gate --dry-run --json)"
[[ "$(echo "${qg_dry}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL quality-gate dry-run not ok" >&2
  exit 1
}

qg_apply="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile quality-gate --json)"
[[ "$(echo "${qg_apply}" | jq -r '.ok')" == "true" ]] || {
  echo "[claude-hooks-test] FAIL quality-gate apply not ok" >&2
  exit 1
}

# Verify the quality gate script was installed
[[ -f "${CLAUDE_DIR}/hooks/stop_quality_gate.sh" ]] || {
  echo "[claude-hooks-test] FAIL missing stop_quality_gate.sh after quality-gate apply" >&2
  exit 1
}
[[ -x "${CLAUDE_DIR}/hooks/stop_quality_gate.sh" ]] || {
  echo "[claude-hooks-test] FAIL stop_quality_gate.sh not executable" >&2
  exit 1
}

# Verify prompt-type Stop hook was removed
prompt_hooks=$(jq '[.hooks.Stop[]?.hooks[]? | select(.type == "prompt")] | length' "${CLAUDE_DIR}/settings.json")
[[ "${prompt_hooks}" == "0" ]] || {
  echo "[claude-hooks-test] FAIL expected prompt-type Stop hooks removed, found ${prompt_hooks}" >&2
  exit 1
}

# Verify command-type Stop hook was added with quality gate
qg_cmd=$(jq -r '.hooks.Stop[-1].hooks[-1].command' "${CLAUDE_DIR}/settings.json")
echo "${qg_cmd}" | /usr/bin/grep -q "stop_quality_gate" || {
  echo "[claude-hooks-test] FAIL expected Stop hook command to reference stop_quality_gate, got: ${qg_cmd}" >&2
  exit 1
}

# Verify timeout was set
qg_timeout=$(jq -r '.hooks.Stop[-1].hooks[-1].timeout // 0' "${CLAUDE_DIR}/settings.json")
[[ "${qg_timeout}" == "30000" ]] || {
  echo "[claude-hooks-test] FAIL expected timeout 30000, got ${qg_timeout}" >&2
  exit 1
}

# Verify idempotency — applying again shouldn't duplicate
qg_apply2="$("${ROOT}/bin/lacp-claude-hooks" apply-profile --claude-dir "${CLAUDE_DIR}" --profile quality-gate --json)"
stop_count=$(jq '[.hooks.Stop[]?.hooks[]? | select(.command and (.command | test("stop_quality_gate")))] | length' "${CLAUDE_DIR}/settings.json")
[[ "${stop_count}" == "1" ]] || {
  echo "[claude-hooks-test] FAIL expected 1 quality gate Stop hook after double apply, got ${stop_count}" >&2
  exit 1
}

echo "[claude-hooks-test] claude hooks tests passed"
