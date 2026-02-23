#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
TAG="v0.0.0-ci-release-verify"
STUBS="${TMP}/stubs"
mkdir -p "${STUBS}"
trap 'rm -rf "${TMP}"; git -C "${ROOT}" tag -d "${TAG}" >/dev/null 2>&1 || true' EXIT

git -C "${ROOT}" tag -f "${TAG}" >/dev/null

cat > "${STUBS}/brew" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
if [[ "${1:-}" == "install" ]]; then
  shift
  for arg in "$@"; do
    if [[ "${arg}" == "--dry-run" ]]; then
      exit 0
    fi
  done
  exit 1
fi
exit 0
EOF
chmod +x "${STUBS}/brew"

json_out="$(
  PATH="${STUBS}:${PATH}" "${ROOT}/bin/lacp-release-verify" \
    --tag "${TAG}" \
    --skip-prepare \
    --allow-dirty \
    --output-dir "${TMP}/out" \
    --json
)"

echo "${json_out}" | jq -e '.kind == "release_verify"' >/dev/null
echo "${json_out}" | jq -e '.ok == true' >/dev/null
echo "${json_out}" | jq -e '.checks.sha256_verified == true' >/dev/null
echo "${json_out}" | jq -e '.checks.archive_prefix_verified == true' >/dev/null
echo "${json_out}" | jq -e '.checks.brew_install_dry_run.ok == true' >/dev/null

archive_path="$(echo "${json_out}" | jq -r '.artifacts.archive')"
checksums_path="$(echo "${json_out}" | jq -r '.artifacts.checksums')"
[[ -f "${archive_path}" ]] || { echo "[release-verify-test] missing archive" >&2; exit 1; }
[[ -f "${checksums_path}" ]] || { echo "[release-verify-test] missing checksums" >&2; exit 1; }

echo "[release-verify-test] release verify tests passed"
