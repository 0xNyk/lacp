#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

lessons_file="${TMP}/lessons.md"
cat > "${lessons_file}" <<'EOF'
# Lessons

- Keep changes minimal.
- Keep changes minimal.
EOF

set +e
"${ROOT}/bin/lacp-lessons" lint --file "${lessons_file}" --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[lessons-test] FAIL expected lint failure for duplicate lessons" >&2
  exit 1
fi

"${ROOT}/bin/lacp-lessons" add-rule --file "${lessons_file}" --rule "Run tests before done." --json | jq -e '.ok == true' >/dev/null
"${ROOT}/bin/lacp-lessons" lint --file "${lessons_file}" --json >/dev/null || true

echo "[lessons-test] lessons command tests passed"
