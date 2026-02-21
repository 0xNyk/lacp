#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
ENV_FILE="${ROOT}/.env"
ENV_BACKUP="${TMP}/.env.backup"
POLICY_FILE="${ROOT}/config/sandbox-policy.json"
POLICY_BACKUP="${TMP}/sandbox-policy.backup.json"

cleanup() {
  if [[ -f "${ENV_BACKUP}" ]]; then
    cp "${ENV_BACKUP}" "${ENV_FILE}"
  else
    rm -f "${ENV_FILE}"
  fi
  cp "${POLICY_BACKUP}" "${POLICY_FILE}"
  rm -rf "${TMP}"
}
trap cleanup EXIT

if [[ -f "${ENV_FILE}" ]]; then
  cp "${ENV_FILE}" "${ENV_BACKUP}"
fi
cp "${POLICY_FILE}" "${POLICY_BACKUP}"

list_json="$("/bin/bash" "${ROOT}/bin/lacp-policy-pack" list --json)"
[[ "$(echo "${list_json}" | jq -r '.ok')" == "true" ]] || { echo "[policy-pack-test] FAIL list not ok" >&2; exit 1; }
[[ "$(echo "${list_json}" | jq -r '.packs | length')" -ge 3 ]] || { echo "[policy-pack-test] FAIL expected >= 3 packs" >&2; exit 1; }

dry_json="$("/bin/bash" "${ROOT}/bin/lacp-policy-pack" apply --pack starter --dry-run --json)"
[[ "$(echo "${dry_json}" | jq -r '.ok')" == "true" ]] || { echo "[policy-pack-test] FAIL starter dry-run not ok" >&2; exit 1; }
[[ "$(echo "${dry_json}" | jq -r '.dry_run')" == "true" ]] || { echo "[policy-pack-test] FAIL starter dry_run false" >&2; exit 1; }

strict_json="$("/bin/bash" "${ROOT}/bin/lacp-policy-pack" apply --pack strict --json)"
[[ "$(echo "${strict_json}" | jq -r '.ok')" == "true" ]] || { echo "[policy-pack-test] FAIL strict apply not ok" >&2; exit 1; }
[[ "$(jq -r '.routing.cost_ceiling_usd_by_risk_tier.review' "${POLICY_FILE}")" == "2" || "$(jq -r '.routing.cost_ceiling_usd_by_risk_tier.review' "${POLICY_FILE}")" == "2.0" ]] || {
  echo "[policy-pack-test] FAIL strict review ceiling not applied" >&2
  exit 1
}
rg -q '^LACP_ALLOW_EXTERNAL_REMOTE="false"' "${ENV_FILE}" || { echo "[policy-pack-test] FAIL strict env update missing" >&2; exit 1; }

enterprise_json="$("/bin/bash" "${ROOT}/bin/lacp-policy-pack" apply --pack enterprise --json)"
[[ "$(echo "${enterprise_json}" | jq -r '.ok')" == "true" ]] || { echo "[policy-pack-test] FAIL enterprise apply not ok" >&2; exit 1; }
[[ "$(jq -r '.routing.cost_ceiling_usd_by_risk_tier.review' "${POLICY_FILE}")" == "20" || "$(jq -r '.routing.cost_ceiling_usd_by_risk_tier.review' "${POLICY_FILE}")" == "20.0" ]] || {
  echo "[policy-pack-test] FAIL enterprise review ceiling not applied" >&2
  exit 1
}
rg -q '^LACP_ALLOW_EXTERNAL_REMOTE="true"' "${ENV_FILE}" || { echo "[policy-pack-test] FAIL enterprise env update missing" >&2; exit 1; }

echo "[policy-pack-test] policy pack tests passed"
