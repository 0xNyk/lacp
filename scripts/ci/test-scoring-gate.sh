#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[scoring-gate-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

# --- Test 1: ScoringResult weighted average ---
avg=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import ScoringResult
r = ScoringResult(completeness=4, honesty=5, deferral_ratio=4, work_evidence=3)
print(f'{r.weighted_avg:.2f}')
")
assert_eq "scoring weighted avg (4,5,4,3)" "4.15" "${avg}"

# --- Test 2: Low scores below threshold ---
below=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import ScoringResult, QUALITY_GATE_THRESHOLD
r = ScoringResult(completeness=1, honesty=2, deferral_ratio=1, work_evidence=1)
print('below' if r.weighted_avg < QUALITY_GATE_THRESHOLD else 'above')
")
assert_eq "low scores below threshold" "below" "${below}"

# --- Test 3: Parse valid scoring JSON ---
parsed=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import _parse_scoring_result
r = _parse_scoring_result('{\"completeness\": 3, \"honesty\": 3, \"deferral_ratio\": 3, \"work_evidence\": 3, \"reasoning\": \"ok\"}')
print('ok' if r is not None and r.completeness == 3.0 else 'fail')
")
assert_eq "parse valid scoring JSON" "ok" "${parsed}"

# --- Test 4: Parse invalid JSON returns None ---
invalid=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import _parse_scoring_result
r = _parse_scoring_result('not json')
print('none' if r is None else 'fail')
")
assert_eq "parse invalid JSON → None" "none" "${invalid}"

# --- Test 5: Code fence stripping ---
fenced=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import _parse_scoring_result
r = _parse_scoring_result('\`\`\`json\n{\"completeness\": 5, \"honesty\": 5, \"deferral_ratio\": 5, \"work_evidence\": 5, \"reasoning\": \"great\"}\n\`\`\`')
print('ok' if r is not None and r.completeness == 5.0 else 'fail')
")
assert_eq "code fence stripped" "ok" "${fenced}"

# --- Test 6: Sprint criteria section builder ---
sprint=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['CLAUDE_SESSION_ID'] = 'test-sprint-scoring'
from hook_contracts import SprintContract, write_contract
from stop_quality_gate import _build_sprint_criteria_section, Context
sc = SprintContract(acceptance_criteria=['auth works', 'tests pass'], expected_files=[], expected_tests=[], agreed_at='2026-03-27')
write_contract('sprint_contract', sc, 'test-sprint-scoring')
ctx = Context(hook_input={}, session_id='test-sprint-scoring', cwd='', last_message='', stripped='', transcript_path='', stop_hook_active=False, ralph_active=False)
section = _build_sprint_criteria_section(ctx)
print('ok' if 'auth works' in section and 'tests pass' in section else 'fail')
")
assert_eq "sprint criteria section" "ok" "${sprint}"

# Cleanup sprint test contract
python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from hook_contracts import cleanup_contracts
cleanup_contracts('test-sprint-scoring')
"

# --- Test 7: Transcript cache works ---
cached=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import _transcript_cache, _cached_scan_transcript
# Cache should start empty
print(len(_transcript_cache))
")
assert_eq "transcript cache starts empty" "0" "${cached}"

# --- Test 8: Threshold env var ---
threshold=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from stop_quality_gate import QUALITY_GATE_THRESHOLD
print(QUALITY_GATE_THRESHOLD)
")
assert_eq "default threshold is 2.5" "2.5" "${threshold}"

# --- Test 9: Scoring prompt has calibration examples ---
has_examples=$(grep -c "Example [0-9]" "${ROOT}/hooks/stop_quality_gate.py")
[[ "${has_examples}" -ge 3 ]] && pass=$((pass + 1)) || { echo "[scoring-gate-test] FAIL fewer than 3 calibration examples" >&2; fail=$((fail + 1)); }

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[scoring-gate-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[scoring-gate-test] all ${total} tests passed"
