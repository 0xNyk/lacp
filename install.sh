#!/usr/bin/env bash
set -euo pipefail

# Hardcoded repo slug — do not accept from environment (M4: CWE-494)
REPO_SLUG="0xNyk/lacp"
REF="${LACP_REF:-main}"
INSTALL_DIR="${LACP_INSTALL_DIR:-$HOME/.lacp}"
WITH_VERIFY="${LACP_WITH_VERIFY:-1}"
PROFILE="${LACP_INSTALL_PROFILE:-starter}"

usage() {
  cat <<'EOF'
Usage: install.sh [--ref <git-ref>] [--dir <install-dir>] [--profile starter|existing] [--with-verify true|false]

Downloads LACP from GitHub archive, installs to target directory, and runs lacp-install.
EOF
}

as_bool() {
  case "$1" in
    true|false) printf '%s' "$1" ;;
    *) echo "Expected true|false, got: $1" >&2; exit 1 ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      REF="$2"
      shift 2
      ;;
    --dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --with-verify)
      WITH_VERIFY="$(as_bool "$2")"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

case "${PROFILE}" in
  starter|existing) ;;
  *) echo "--profile must be starter|existing" >&2; exit 1 ;;
esac

for cmd in curl tar mktemp; do
  command -v "${cmd}" >/dev/null 2>&1 || { echo "Missing required command: ${cmd}" >&2; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/heads/${REF}.tar.gz"
if [[ "${REF}" == v* ]]; then
  ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/tags/${REF}.tar.gz"
fi

echo "[lacp-install] downloading ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" -o "${TMP}/lacp.tar.gz"

# Verify archive integrity if LACP_EXPECTED_SHA256 is set (M4: CWE-494)
if [[ -n "${LACP_EXPECTED_SHA256:-}" ]]; then
  actual_sha256="$(shasum -a 256 "${TMP}/lacp.tar.gz" | cut -d' ' -f1)"
  if [[ "${actual_sha256}" != "${LACP_EXPECTED_SHA256}" ]]; then
    echo "[lacp-install] FATAL: SHA-256 mismatch! Expected: ${LACP_EXPECTED_SHA256}, Got: ${actual_sha256}" >&2
    exit 1
  fi
  echo "[lacp-install] SHA-256 verified: ${actual_sha256}"
fi

tar -xzf "${TMP}/lacp.tar.gz" -C "${TMP}"

SRC_DIR="$(find "${TMP}" -maxdepth 1 -type d -name 'lacp-*' | head -n 1)"
[[ -n "${SRC_DIR}" ]] || { echo "Could not find extracted source dir" >&2; exit 1; }

mkdir -p "$(dirname "${INSTALL_DIR}")"
rm -rf "${INSTALL_DIR}"
mv "${SRC_DIR}" "${INSTALL_DIR}"

echo "[lacp-install] installed to ${INSTALL_DIR}"
cd "${INSTALL_DIR}"

ARGS=(--profile "${PROFILE}")
if [[ "${WITH_VERIFY}" == "true" ]]; then
  ARGS+=(--with-verify)
fi

./bin/lacp-install "${ARGS[@]}"
echo "[lacp-install] done"
