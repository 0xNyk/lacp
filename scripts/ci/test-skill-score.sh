#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

LABEL="skill-score"

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    echo "[${LABEL}] PASS ${label}"
  else
    echo "[${LABEL}] FAIL ${label}: expected '${expected}', got '${actual}'" >&2
    exit 1
  fi
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if echo "${haystack}" | grep -qF "${needle}"; then
    echo "[${LABEL}] PASS ${label}"
  else
    echo "[${LABEL}] FAIL ${label}: '${needle}' not found" >&2
    echo "--- output ---"
    echo "${haystack}"
    echo "--- end ---"
    exit 1
  fi
}

# --- Setup: create a test ledger with known workflows ---
LEDGER="${TMP}/workflow_ledger.json"
NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

cat > "${LEDGER}" <<JSON
{
  "version": 1,
  "updated_at": "${NOW}",
  "workflows": {
    "wf-high": {
      "signature": "high-confidence-wf",
      "purpose": "test high confidence",
      "steps": ["step1", "step2", "step3"],
      "count": 10,
      "success_count": 10,
      "validation_count": 10,
      "validation_runs": 10,
      "first_seen": "${NOW}",
      "last_seen": "${NOW}",
      "decay_class": "procedure",
      "sessions": [{"fingerprint": "abc", "branch": "main", "project": "lacp", "timestamp": "${NOW}"}]
    },
    "wf-low": {
      "signature": "low-confidence-wf",
      "purpose": "test low confidence",
      "steps": ["step1"],
      "count": 2,
      "success_count": 1,
      "validation_count": 0,
      "validation_runs": 0,
      "first_seen": "2025-01-01T00:00:00+00:00",
      "last_seen": "2025-01-01T00:00:00+00:00",
      "decay_class": "ephemeral"
    },
    "wf-arch": {
      "signature": "architecture-wf",
      "purpose": "test architecture never decays",
      "steps": ["step1", "step2"],
      "count": 5,
      "success_count": 5,
      "validation_count": 5,
      "validation_runs": 5,
      "first_seen": "2025-01-01T00:00:00+00:00",
      "last_seen": "2025-01-01T00:00:00+00:00",
      "decay_class": "architecture"
    }
  },
  "signature_aliases": {}
}
JSON

# --- Test 1: recalc computes confidence ---
out="$(bash "${ROOT}/bin/lacp-skill-score" recalc --ledger "${LEDGER}")"
assert_contains "${out}" '"ok": true' "recalc_ok"
assert_contains "${out}" '"updated": 3' "recalc_updated_count"

# Verify confidence was written to ledger
high_conf="$(jq -r '.workflows["wf-high"].confidence' "${LEDGER}")"
low_conf="$(jq -r '.workflows["wf-low"].confidence' "${LEDGER}")"
arch_conf="$(jq -r '.workflows["wf-arch"].confidence' "${LEDGER}")"

# High should be near 1.0 (perfect success, recent, 10 obs)
if (( $(echo "${high_conf} > 0.8" | bc -l) )); then
  echo "[${LABEL}] PASS high_confidence_value (${high_conf})"
else
  echo "[${LABEL}] FAIL high_confidence_value: expected >0.8, got ${high_conf}" >&2
  exit 1
fi

# Low should be very low (50% success, 0 validation, old, 2 obs)
if (( $(echo "${low_conf} < 0.4" | bc -l) )); then
  echo "[${LABEL}] PASS low_confidence_value (${low_conf})"
else
  echo "[${LABEL}] FAIL low_confidence_value: expected <0.4, got ${low_conf}" >&2
  exit 1
fi

# Architecture should have recency_boost=1.0 (never decays)
# Architecture recency_boost must be 1 (never decays)
arch_recency="$(jq -r '.workflows["wf-arch"].confidence_factors.recency_boost' "${LEDGER}")"
if (( $(echo "${arch_recency} == 1.0" | bc -l) )); then
  echo "[${LABEL}] PASS architecture_no_decay (recency_boost=${arch_recency})"
else
  echo "[${LABEL}] FAIL architecture_no_decay: expected 1.0, got ${arch_recency}" >&2
  exit 1
fi

# --- Test 2: report outputs correct totals ---
report="$(bash "${ROOT}/bin/lacp-skill-score" report --json --ledger "${LEDGER}")"
total="$(echo "${report}" | jq -r '.total_workflows')"
assert_eq "${total}" "3" "report_total"

high_bucket="$(echo "${report}" | jq -r '.by_confidence.high')"
with_sessions="$(echo "${report}" | jq -r '.with_sessions')"
assert_eq "${with_sessions}" "1" "report_sessions"

# --- Test 3: report text mode ---
report_text="$(bash "${ROOT}/bin/lacp-skill-score" report --ledger "${LEDGER}")"
assert_contains "${report_text}" "Total workflows: 3" "report_text_total"
assert_contains "${report_text}" "Skill Score Report" "report_text_header"

# --- Test 4: prune archives low-confidence workflows ---
out="$(bash "${ROOT}/bin/lacp-skill-score" prune --below 0.4 --ledger "${LEDGER}")"
assert_contains "${out}" '"ok": true' "prune_ok"

pruned_count="$(echo "${out}" | jq -r '.pruned')"
if [[ "${pruned_count}" -ge 1 ]]; then
  echo "[${LABEL}] PASS prune_removed_low (${pruned_count} pruned)"
else
  echo "[${LABEL}] FAIL prune_removed_low: expected >=1, got ${pruned_count}" >&2
  exit 1
fi

# Verify archived_workflows key exists
archived="$(jq -r '.archived_workflows | length' "${LEDGER}")"
if [[ "${archived}" -ge 1 ]]; then
  echo "[${LABEL}] PASS prune_archived_stored (${archived} archived)"
else
  echo "[${LABEL}] FAIL prune_archived_stored: expected >=1, got ${archived}" >&2
  exit 1
fi

# Verify pruned workflow has archive metadata
has_reason="$(jq -r '.archived_workflows["wf-low"].archive_reason // empty' "${LEDGER}")"
if [[ -n "${has_reason}" ]]; then
  echo "[${LABEL}] PASS prune_archive_reason"
else
  echo "[${LABEL}] FAIL prune_archive_reason: missing archive_reason" >&2
  exit 1
fi

echo "[${LABEL}] all skill-score tests passed"
