#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[brain-ingest-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[brain-ingest-test] PASS ${label}"
}

export HOME="${TMP}/home"
export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${HOME}/.lacp/automation"
mkdir -p "${LACP_AUTOMATION_ROOT}/scripts" "${HOME}/obsidian/vault/inbox"

DELEGATE_ARGS_FILE="${TMP}/delegate-args.txt"
export DELEGATE_ARGS_FILE

cat > "${LACP_AUTOMATION_ROOT}/scripts/brain-ingest.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "${DELEGATE_ARGS_FILE}"
echo "delegate-ok"
EOF
chmod +x "${LACP_AUTOMATION_ROOT}/scripts/brain-ingest.sh"

text_file="${TMP}/notes.md"
printf 'hello world\n' > "${text_file}"

text_json="$("${ROOT}/bin/lacp" brain-ingest "${text_file}" --apply --json)"
assert_eq "$(echo "${text_json}" | jq -r '.ok')" "true" "text_delegate.ok"
assert_eq "$(echo "${text_json}" | jq -r '.input_kind')" "text" "text_delegate.kind"
assert_eq "$(sed -n '1p' "${DELEGATE_ARGS_FILE}")" "--transcript" "text_delegate.arg1"
assert_eq "$(sed -n '2p' "${DELEGATE_ARGS_FILE}")" "${text_file}" "text_delegate.arg2"
assert_eq "$(sed -n '3p' "${DELEGATE_ARGS_FILE}")" "--title" "text_delegate.arg3"
assert_eq "$(sed -n '5p' "${DELEGATE_ARGS_FILE}")" "--apply" "text_delegate.apply"

media_file="${TMP}/clip.mp4"
: > "${media_file}"

media_json="$("${ROOT}/bin/lacp" brain-ingest "${media_file}" --json)"
assert_eq "$(echo "${media_json}" | jq -r '.ok')" "true" "media_delegate.ok"
assert_eq "$(echo "${media_json}" | jq -r '.input_kind')" "media_file" "media_delegate.kind"
assert_eq "$(sed -n '1p' "${DELEGATE_ARGS_FILE}")" "${media_file}" "media_delegate.arg1"

link_json="$("${ROOT}/bin/lacp" brain-ingest "https://example.com/articles/lacp" --apply --json)"
assert_eq "$(echo "${link_json}" | jq -r '.ok')" "true" "link_capture.ok"
assert_eq "$(echo "${link_json}" | jq -r '.mode')" "link_note" "link_capture.mode"
assert_eq "$(echo "${link_json}" | jq -r '.schema_valid')" "true" "link_capture.schema_valid"
assert_eq "$(echo "${link_json}" | jq -r '.quality_gate.required_fields_present')" "true" "link_capture.quality_gate.required_fields_present"
assert_eq "$(echo "${link_json}" | jq -r '.quality_gate.provenance_present')" "true" "link_capture.quality_gate.provenance_present"
note_path="$(echo "${link_json}" | jq -r '.note_path')"
if [[ ! -f "${note_path}" ]]; then
  echo "[brain-ingest-test] FAIL link_capture.note_missing: ${note_path}" >&2
  exit 1
fi
if ! rg -q 'source: link-ingest' "${note_path}"; then
  echo "[brain-ingest-test] FAIL link_capture.note_content.source" >&2
  exit 1
fi
if ! rg -q 'layer: 3' "${note_path}"; then
  echo "[brain-ingest-test] FAIL link_capture.note_content.layer" >&2
  exit 1
fi
if ! rg -q 'confidence: 0.6' "${note_path}"; then
  echo "[brain-ingest-test] FAIL link_capture.note_content.confidence" >&2
  exit 1
fi
if ! rg -q 'source_urls:' "${note_path}"; then
  echo "[brain-ingest-test] FAIL link_capture.note_content.source_urls" >&2
  exit 1
fi

echo "[brain-ingest-test] brain-ingest tests passed"
