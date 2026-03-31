#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

HOOK="${ROOT}/hooks/thinking_nudge.py"

# Use unique session IDs to avoid cooldown state from previous runs
RUN_ID="$$_$(date +%s)"

# Clean up any stale state from previous test runs
rm -rf "${HOME}/.lacp/hooks/state/tn_"* 2>/dev/null || true

# Test 1: disabled by default — no output
result="$(echo "{\"prompt\":\"What should I do about my architecture?\",\"session_id\":\"tn_${RUN_ID}_1\"}" | LACP_THINKING_NUDGE=0 python3 "${HOOK}" 2>/dev/null)"
if [[ -n "${result}" ]]; then
  echo "FAIL: nudge should not fire when disabled" >&2
  exit 1
fi

# Test 2: enabled + bare question → nudge
export LACP_THINKING_NUDGE=1
result="$(echo "{\"prompt\":\"What should I do about my architecture design for the new microservices system?\",\"session_id\":\"tn_${RUN_ID}_2\"}" | python3 "${HOOK}" 2>/dev/null)"
if ! echo "${result}" | jq -e '.systemMessage' >/dev/null 2>&1; then
  echo "FAIL: nudge should fire for bare question" >&2
  exit 1
fi

# Test 3: enabled + position stated → no nudge
result="$(echo "{\"prompt\":\"I think we should use event sourcing because it gives us audit trails. What are the tradeoffs?\",\"session_id\":\"tn_${RUN_ID}_3\"}" | python3 "${HOOK}" 2>/dev/null)"
if [[ -n "${result}" ]]; then
  echo "FAIL: nudge should not fire when position is stated" >&2
  exit 1
fi

# Test 4: implementation command → no nudge
result="$(echo "{\"prompt\":\"Fix the authentication bug in the login handler and add a test\",\"session_id\":\"tn_${RUN_ID}_4\"}" | python3 "${HOOK}" 2>/dev/null)"
if [[ -n "${result}" ]]; then
  echo "FAIL: nudge should not fire for implementation commands" >&2
  exit 1
fi

# Test 5: short prompt → no nudge
result="$(echo "{\"prompt\":\"What is this?\",\"session_id\":\"tn_${RUN_ID}_5\"}" | python3 "${HOOK}" 2>/dev/null)"
if [[ -n "${result}" ]]; then
  echo "FAIL: nudge should not fire for short prompts" >&2
  exit 1
fi

# Test 6: context mode activation
result="$(echo "{\"prompt\":\"How should I structure the API endpoints for the new billing system?\",\"session_id\":\"tn_${RUN_ID}_6\"}" | LACP_THINKING_NUDGE=0 LACP_CONTEXT_MODE=thinking-partner python3 "${HOOK}" 2>/dev/null)"
if ! echo "${result}" | jq -e '.systemMessage' >/dev/null 2>&1; then
  echo "FAIL: nudge should fire when context mode is thinking-partner" >&2
  exit 1
fi

echo "[thinking-nudge-test] all tests passed"
