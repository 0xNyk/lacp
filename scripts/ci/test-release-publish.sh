#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
TAG="v0.0.0-ci-release-publish"
trap 'rm -rf "${TMP}"; git -C "${ROOT}" tag -d "${TAG}" >/dev/null 2>&1 || true' EXIT

git -C "${ROOT}" tag -f "${TAG}" >/dev/null

json_out="$("${ROOT}/bin/lacp-release-publish" \
  --tag "${TAG}" \
  --skip-prepare \
  --skip-gh \
  --allow-dirty \
  --output-dir "${TMP}/out" \
  --json)"

echo "${json_out}" | jq -e '.kind == "release_publish"' >/dev/null
echo "${json_out}" | jq -e '.ok == true' >/dev/null
echo "${json_out}" | jq -e '.options.skip_gh == true' >/dev/null
echo "${json_out}" | jq -e '.github_release.action == "skipped"' >/dev/null

archive_path="$(echo "${json_out}" | jq -r '.artifacts.archive')"
checksums_path="$(echo "${json_out}" | jq -r '.artifacts.checksums')"

[[ -f "${archive_path}" ]] || { echo "[release-publish-test] missing archive" >&2; exit 1; }
[[ -f "${checksums_path}" ]] || { echo "[release-publish-test] missing SHA256SUMS" >&2; exit 1; }

(cd "$(dirname "${checksums_path}")" && shasum -a 256 -c "$(basename "${checksums_path}")" >/dev/null)

echo "[release-publish-test] release publish tests passed"
