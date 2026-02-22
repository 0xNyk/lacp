#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "${ROOT}"

# Enforce strict shell mode on executable bash scripts in bin/scripts.
violations="$(rg -l '^#!/usr/bin/env bash' bin scripts \
  | xargs -I{} sh -c 'rg -q "set -euo pipefail" "{}" || echo "{}"')"
if [[ -n "${violations}" ]]; then
  echo "[shell-hardening-test] FAIL missing strict mode in:" >&2
  echo "${violations}" >&2
  exit 1
fi

# Reject risky supply-chain patterns in executable surfaces.
if rg -n \
  --glob='bin/**' \
  --glob='scripts/**' \
  --glob='!scripts/ci/test-*.sh' \
  --glob='!bin/lacp-skill-audit' \
  '(curl|wget).*\|\s*(bash|sh)\b' >/dev/null; then
  echo "[shell-hardening-test] FAIL found curl/wget pipe-to-shell pattern in bin/scripts" >&2
  rg -n \
    --glob='bin/**' \
    --glob='scripts/**' \
    --glob='!scripts/ci/test-*.sh' \
    --glob='!bin/lacp-skill-audit' \
    '(curl|wget).*\|\s*(bash|sh)\b' >&2
  exit 1
fi

if rg -n \
  --glob='bin/**' \
  --glob='scripts/**' \
  --glob='!scripts/ci/test-*.sh' \
  'eval[[:space:]]+["'\'']?\$\(' >/dev/null; then
  echo "[shell-hardening-test] FAIL found eval \$(...) pattern in bin/scripts" >&2
  rg -n \
    --glob='bin/**' \
    --glob='scripts/**' \
    --glob='!scripts/ci/test-*.sh' \
    'eval[[:space:]]+["'\'']?\$\(' >&2
  exit 1
fi

echo "[shell-hardening-test] shell and hooks hardening tests passed"
