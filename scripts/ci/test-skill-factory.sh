#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

FACTORY_ROOT="${TMP}/auto-skill-factory"
mkdir -p "${FACTORY_ROOT}/scripts" "${FACTORY_ROOT}/state"

cat > "${FACTORY_ROOT}/scripts/record_workflow.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "record"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/record_workflow.py"

cat > "${FACTORY_ROOT}/scripts/capture_validation.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "capture"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/capture_validation.py"

cat > "${FACTORY_ROOT}/scripts/manage_lifecycle.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "lifecycle"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/manage_lifecycle.py"

cat > "${FACTORY_ROOT}/scripts/recluster_workflows.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "recluster"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/recluster_workflows.py"

cat > "${FACTORY_ROOT}/scripts/revalidate_autogen_skills.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "revalidate"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/revalidate_autogen_skills.py"

cat > "${FACTORY_ROOT}/scripts/migrate_category_bundles.py" <<'PY'
#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "tool": "migrate-bundles"}))
PY
chmod +x "${FACTORY_ROOT}/scripts/migrate_category_bundles.py"

cat > "${FACTORY_ROOT}/state/workflow_ledger.json" <<'JSON'
{
  "version": 1,
  "updated_at": "2026-02-21T00:00:00+00:00",
  "workflows": {
    "wf-a": {"count": 1, "autogen_skill": null},
    "wf-b": {"count": 3, "autogen_skill": "autogen-docs"}
  },
  "signature_aliases": {}
}
JSON

summary="$("${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" summary)"
echo "${summary}" | jq -e '.ok == true' >/dev/null
echo "${summary}" | jq -e '.workflow_count == 2' >/dev/null
echo "${summary}" | jq -e '.workflows_gt1 == 1' >/dev/null

# --root should work after the command as well.
"${ROOT}/bin/lacp-skill-factory" summary --root "${FACTORY_ROOT}" >/dev/null

"${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" capture >/dev/null
"${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" lifecycle >/dev/null
"${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" recluster >/dev/null
"${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" revalidate >/dev/null
"${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" migrate-bundles >/dev/null

echo '{"signature":"x","purpose":"y","steps":["a"],"success":false}' \
  | "${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" record >/dev/null

# Missing script should fail with explicit command-scoped message.
rm -f "${FACTORY_ROOT}/scripts/migrate_category_bundles.py"
set +e
missing_out="$("${ROOT}/bin/lacp-skill-factory" --root "${FACTORY_ROOT}" migrate-bundles 2>&1)"
missing_rc=$?
set -e
if [[ "${missing_rc}" -eq 0 ]]; then
  echo "[skill-factory-test] FAIL expected missing script failure" >&2
  exit 1
fi
echo "${missing_out}" | rg -q "Missing required script for command 'migrate-bundles'" || {
  echo "[skill-factory-test] FAIL missing-script error message mismatch" >&2
  exit 1
}

echo "[skill-factory-test] skill factory tests passed"
