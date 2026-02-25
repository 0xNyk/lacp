#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS_DIR="${ROOT}/config/harness"

schema_file="${HARNESS_DIR}/tasks.schema.json"
profiles_file="${HARNESS_DIR}/sandbox-profiles.yaml"
verify_file="${HARNESS_DIR}/verification-policy.yaml"
browser_schema_file="${HARNESS_DIR}/browser-evidence.schema.json"
risk_contract_file="${ROOT}/config/risk-policy-contract.json"
risk_contract_schema_file="${ROOT}/config/risk-policy-contract.schema.json"

[[ -f "${schema_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${schema_file}" >&2; exit 1; }
[[ -f "${profiles_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${profiles_file}" >&2; exit 1; }
[[ -f "${verify_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${verify_file}" >&2; exit 1; }
[[ -f "${browser_schema_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${browser_schema_file}" >&2; exit 1; }
[[ -f "${risk_contract_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${risk_contract_file}" >&2; exit 1; }
[[ -f "${risk_contract_schema_file}" ]] || { echo "[harness-contracts-test] FAIL missing ${risk_contract_schema_file}" >&2; exit 1; }

jq -e '.["$schema"] and .properties.tasks and .properties.tasks.items.properties.sandbox_profile and .properties.tasks.items.properties.verification_policy and .properties.tasks.items.properties.expected_inputs and .properties.tasks.items.properties.expected_outputs' "${schema_file}" >/dev/null
jq -e '.["$schema"] and .properties.flows and .properties.captured_at_utc' "${browser_schema_file}" >/dev/null
jq -e '.version and .riskTierRules and .mergePolicy and .docsDriftRules and .reviewAgent and .browserEvidence and .apiEvidence and .contractEvidence' "${risk_contract_file}" >/dev/null
jq -e '.["$schema"] and .properties.riskTierRules and .properties.mergePolicy and .properties.docsDriftRules' "${risk_contract_schema_file}" >/dev/null

ruby -e '
require "yaml"
profiles = YAML.load_file(ARGV[0])
verify = YAML.load_file(ARGV[1])
raise "profiles hash missing" unless profiles.is_a?(Hash)
raise "verify hash missing" unless verify.is_a?(Hash)
raise "profiles.default_profile missing" unless profiles["default_profile"].is_a?(String)
raise "profiles.profiles missing" unless profiles["profiles"].is_a?(Hash) && !profiles["profiles"].empty?
raise "profiles.default_profile not found in profiles map" unless profiles["profiles"].key?(profiles["default_profile"])
raise "verification.default_policy missing" unless verify["default_policy"].is_a?(String)
raise "verification.policies missing" unless verify["policies"].is_a?(Hash) && !verify["policies"].empty?
raise "verification.default_policy not found in policies map" unless verify["policies"].key?(verify["default_policy"])
profiles["profiles"].each do |name, cfg|
  raise "profile #{name} missing route" unless cfg.is_a?(Hash) && cfg["route"].is_a?(String)
  raise "profile #{name} missing backend" unless cfg["backend"].is_a?(String)
  raise "profile #{name} missing risk_tier" unless cfg["risk_tier"].is_a?(String)
  raise "profile #{name} invalid route" unless %w[trusted_local local_sandbox remote_sandbox].include?(cfg["route"])
  raise "profile #{name} invalid risk_tier" unless %w[safe review critical].include?(cfg["risk_tier"])
  raise "profile #{name} missing tool_allowlist" unless cfg["tool_allowlist"].is_a?(Array) && !cfg["tool_allowlist"].empty?
end
verify["policies"].each do |name, cfg|
  raise "policy #{name} missing required checks" unless cfg.is_a?(Hash) && cfg.dig("required", "checks").is_a?(Array) && !cfg.dig("required", "checks").empty?
  raise "policy #{name} missing thresholds" unless cfg["thresholds"].is_a?(Hash)
  raise "policy #{name} missing failure_action" unless cfg["failure_action"].is_a?(String)
  raise "policy #{name} invalid failure_action" unless %w[block require_human_review retry_same_model retry_stronger_model].include?(cfg["failure_action"])
end
' "${profiles_file}" "${verify_file}"

echo "[harness-contracts-test] harness contracts tests passed"
