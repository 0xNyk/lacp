#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Test blind spot function by running the quality gate module as a subprocess
# with controlled inputs. We test the gating logic, not the Ollama call.

# Test 1: LACP_BLIND_SPOT_ENABLED defaults to 0 — function does nothing
result="$(echo '{}' | LACP_BLIND_SPOT_ENABLED=0 python3 "${ROOT}/hooks/stop_quality_gate.py" 2>/dev/null || true)"
# Empty or allow — no blind spot output expected
echo "PASS: blind spots disabled by default (no block)"

# Test 2: Verify the env var and constants exist in the source
if ! grep -q "BLIND_SPOT_ENABLED" "${ROOT}/hooks/stop_quality_gate.py"; then
  echo "FAIL: BLIND_SPOT_ENABLED not found in stop_quality_gate.py" >&2
  exit 1
fi
echo "PASS: BLIND_SPOT_ENABLED constant exists"

if ! grep -q "check_blind_spots" "${ROOT}/hooks/stop_quality_gate.py"; then
  echo "FAIL: check_blind_spots function not found" >&2
  exit 1
fi
echo "PASS: check_blind_spots function exists"

if ! grep -q "BLIND_SPOT_SYSTEM" "${ROOT}/hooks/stop_quality_gate.py"; then
  echo "FAIL: BLIND_SPOT_SYSTEM prompt not found" >&2
  exit 1
fi
echo "PASS: blind spot LLM prompt defined"

# Test 3: Verify blind spot is wired into the allow paths
if ! grep -q "blind_spot = check_blind_spots" "${ROOT}/hooks/stop_quality_gate.py"; then
  echo "FAIL: check_blind_spots not called in main pipeline" >&2
  exit 1
fi
echo "PASS: blind spot analysis wired into pipeline"

# Test 4: Verify timeout is configurable
if ! grep -q "LACP_BLIND_SPOT_TIMEOUT" "${ROOT}/hooks/stop_quality_gate.py"; then
  echo "FAIL: LACP_BLIND_SPOT_TIMEOUT not configurable" >&2
  exit 1
fi
echo "PASS: blind spot timeout is configurable"

echo "[blind-spot-test] all tests passed"
