#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"
export LACP_SKIP_DOTENV=1
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_OBSIDIAN_VAULT}" "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

init_json="$(${ROOT}/bin/lacp-brain-stack init --json)"
echo "${init_json}" | jq -e '.ok == true and .dry_run == false' >/dev/null
settings_path="$(echo "${init_json}" | jq -r '.claude_settings')"
[[ -f "${settings_path}" ]] || { echo "[brain-stack-test] missing settings file" >&2; exit 1; }

status_json="$(${ROOT}/bin/lacp-brain-stack status --json)"
echo "${status_json}" | jq -e '.ok == true' >/dev/null

python3 - <<'PY' "${settings_path}"
import json, sys
p = json.load(open(sys.argv[1]))
servers = p.get('mcpServers', {})
required = {'memory','smart-connections','qmd','obsidian'}
missing = required - set(servers.keys())
if missing:
    raise SystemExit(f"missing mcp servers: {sorted(missing)}")
if 'gitnexus' in servers:
    raise SystemExit("gitnexus should not be present without --with-gitnexus")
PY

## --- init with --with-gitnexus ---
gn_json="$(${ROOT}/bin/lacp-brain-stack init --with-gitnexus --json)"
echo "${gn_json}" | jq -e '.ok == true' >/dev/null
python3 - <<'PY' "${settings_path}"
import json, sys
p = json.load(open(sys.argv[1]))
servers = p.get('mcpServers', {})
required = {'memory','smart-connections','qmd','obsidian','gitnexus'}
missing = required - set(servers.keys())
if missing:
    raise SystemExit(f"missing mcp servers after --with-gitnexus: {sorted(missing)}")
gn = servers['gitnexus']
if gn.get('args') != ['-y', 'gitnexus@latest', 'mcp']:
    raise SystemExit(f"unexpected gitnexus args: {gn.get('args')}")
PY

## --- audit subcommand (empty state) ---
audit_json="$(${ROOT}/bin/lacp-brain-stack audit --json)"
echo "${audit_json}" | jq -e '.ok == true and .kind == "brain_stack_audit"' >/dev/null
echo "${audit_json}" | jq -e '.total_projects >= 0' >/dev/null

## --- scaffold-all subcommand ---
# Create fake project dirs with session files but no memory
PROJ_A="${HOME}/.claude/projects/-tmp-proj-alpha"
PROJ_B="${HOME}/.claude/projects/-tmp-proj-beta"
PROJ_C="${HOME}/.claude/projects/-tmp-proj-gamma"
mkdir -p "${PROJ_A}" "${PROJ_B}" "${PROJ_C}"

# proj-alpha: 6 sessions (above default threshold of 5)
for i in 1 2 3 4 5 6; do touch "${PROJ_A}/session-${i}.jsonl"; done

# proj-beta: 3 sessions (below threshold)
for i in 1 2 3; do touch "${PROJ_B}/session-${i}.jsonl"; done

# proj-gamma: 7 sessions but already has memory
mkdir -p "${PROJ_C}/memory"
echo "# existing" > "${PROJ_C}/memory/MEMORY.md"
for i in 1 2 3 4 5 6 7; do touch "${PROJ_C}/session-${i}.jsonl"; done

# dry-run: should report alpha as scaffolded, beta below threshold, gamma skipped
dryrun_json="$(${ROOT}/bin/lacp-brain-stack scaffold-all --min-sessions 5 --dry-run --json)"
echo "${dryrun_json}" | jq -e '.ok == true and .dry_run == true' >/dev/null
echo "${dryrun_json}" | jq -e '.scaffolded >= 1' >/dev/null
# alpha should NOT have memory yet (dry-run)
[[ ! -f "${PROJ_A}/memory/MEMORY.md" ]] || { echo "[brain-stack-test] dry-run created files" >&2; exit 1; }

# real run
scaffold_json="$(${ROOT}/bin/lacp-brain-stack scaffold-all --min-sessions 5 --json)"
echo "${scaffold_json}" | jq -e '.ok == true and .dry_run == false' >/dev/null
echo "${scaffold_json}" | jq -e '.scaffolded >= 1' >/dev/null
# alpha should now have memory
[[ -f "${PROJ_A}/memory/MEMORY.md" ]] || { echo "[brain-stack-test] scaffold-all did not create MEMORY.md for alpha" >&2; exit 1; }
[[ -f "${PROJ_A}/memory/debugging.md" ]] || { echo "[brain-stack-test] scaffold-all did not create debugging.md for alpha" >&2; exit 1; }
[[ -f "${PROJ_A}/memory/patterns.md" ]] || { echo "[brain-stack-test] scaffold-all did not create patterns.md for alpha" >&2; exit 1; }
[[ -f "${PROJ_A}/memory/architecture.md" ]] || { echo "[brain-stack-test] scaffold-all did not create architecture.md for alpha" >&2; exit 1; }
[[ -f "${PROJ_A}/memory/preferences.md" ]] || { echo "[brain-stack-test] scaffold-all did not create preferences.md for alpha" >&2; exit 1; }

# beta should NOT have memory (below threshold)
[[ ! -f "${PROJ_B}/memory/MEMORY.md" ]] || { echo "[brain-stack-test] scaffold-all created memory for below-threshold project" >&2; exit 1; }

# gamma memory should be unchanged (already existed)
grep -q "existing" "${PROJ_C}/memory/MEMORY.md" || { echo "[brain-stack-test] scaffold-all overwrote existing memory" >&2; exit 1; }

# re-run should skip alpha (already scaffolded)
rescan_json="$(${ROOT}/bin/lacp-brain-stack scaffold-all --min-sessions 5 --json)"
alpha_in_projects="$(echo "${rescan_json}" | jq '[.projects[] | select(.slug | test("alpha"))] | length')"
[[ "${alpha_in_projects}" -eq 0 ]] || { echo "[brain-stack-test] scaffold-all re-scaffolded already-done project" >&2; exit 1; }

## --- audit after scaffold ---
post_audit_json="$(${ROOT}/bin/lacp-brain-stack audit --json)"
echo "${post_audit_json}" | jq -e '.with_memory >= 1' >/dev/null

echo "[brain-stack-test] brain stack tests passed"
