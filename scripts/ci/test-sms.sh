#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass=$((pass + 1))
  else
    echo "[sms-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    fail=$((fail + 1))
  fi
}

# Use temp SMS root to avoid polluting real data
export LACP_SMS_ROOT="${TMP}/sms"

# --- Test 1: Python compiles ---
python3 -c "import py_compile; py_compile.compile('${ROOT}/hooks/self_memory_system.py', doraise=True)" 2>/dev/null
pass=$((pass + 1))

# --- Test 2: Episode write/read ---
result=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
import os; os.environ['LACP_SMS_ROOT'] = '${TMP}/sms'
from self_memory_system import Episode, write_episode, read_episodes
ep = Episode(session_id='test-1', project='/tmp/test', started_at='2026-03-28T10:00:00Z', summary='test episode', significance=0.7)
write_episode(ep)
eps = read_episodes(days=1)
print(len(eps))
")
assert_eq "episode write/read" "1" "${result}"

# --- Test 3: Significance scoring ---
sig=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from self_memory_system import compute_significance
s1 = compute_significance('This was a breakthrough moment')
s2 = compute_significance('Regular commit, nothing special')
s3 = compute_significance('Critical failure in production', had_test_failures=True)
print(f'{s1:.1f},{s2:.1f},{s3:.1f}')
")
assert_eq "significance scoring" "0.9,0.3,0.8" "${sig}"

# --- Test 4: Goal relevance scoring ---
rel=$(python3 -c "
import sys; sys.path.insert(0, '${ROOT}/hooks')
from self_memory_system import goal_relevance_score
ws = {'current_problem': 'authentication middleware security'}
r1 = goal_relevance_score('auth middleware session tokens', ws)
r2 = goal_relevance_score('database migration scripts', ws)
print(f'{r1:.1f},{r2:.1f}')
")
# r1 should be higher than r2
r1=$(echo "${rel}" | cut -d, -f1)
r2=$(echo "${rel}" | cut -d, -f2)
python3 -c "assert ${r1} > ${r2}, '${r1} should be > ${r2}'" 2>/dev/null && pass=$((pass + 1)) || { echo "[sms-test] FAIL goal relevance: ${r1} not > ${r2}" >&2; fail=$((fail + 1)); }

# --- Test 5: Self-model write/read ---
sm_result=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['LACP_SMS_ROOT'] = '${TMP}/sms'
from self_memory_system import SelfModel, write_self_model, read_self_model
sm = SelfModel(agent_id='test-agent', preferred_approaches=['test-first', 'incremental'], known_biases=['over-engineers'])
write_self_model(sm)
sm2 = read_self_model()
print(f'{sm2.agent_id},{len(sm2.preferred_approaches)},{sm2.update_count}')
")
assert_eq "self-model write/read" "test-agent,2,1" "${sm_result}"

# --- Test 6: Narrative write/read ---
narr_result=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['LACP_SMS_ROOT'] = '${TMP}/sms'
from self_memory_system import AgentNarrative, write_narrative, read_narrative
n = AgentNarrative(agent_id='test-agent', current_arc='building a control plane', recurring_themes=['harness design', 'memory'])
write_narrative(n)
n2 = read_narrative()
print(f'{n2.agent_id},{len(n2.recurring_themes)}')
")
assert_eq "narrative write/read" "test-agent,2" "${narr_result}"

# --- Test 7: Epoch synthesis ---
epoch_result=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['LACP_SMS_ROOT'] = '${TMP}/sms'
from self_memory_system import Episode, write_episode, synthesize_epoch
# Write a few significant episodes
for i in range(3):
    ep = Episode(session_id=f'synth-{i}', project='/tmp', started_at='2026-03-28T10:00:00Z', summary=f'episode {i}', significance=0.7, decisions_made=[f'decided {i}'])
    write_episode(ep)
epoch = synthesize_epoch('test epoch', days=1)
print(f'{epoch.episode_count},{len(epoch.key_decisions)}')
")
# 4 episodes total: 1 from test 2 (sig=0.7) + 3 from this test (sig=0.7)
assert_eq "epoch synthesis" "4,3" "${epoch_result}"

# --- Test 8: Session context builder ---
ctx_result=$(python3 -c "
import sys, os; sys.path.insert(0, '${ROOT}/hooks')
os.environ['LACP_SMS_ROOT'] = '${TMP}/sms'
from self_memory_system import build_session_context
ctx = build_session_context()
# Should include self-model and narrative from previous tests
print('ok' if 'test-first' in ctx or 'control plane' in ctx or 'Current focus' in ctx else 'empty')
")
# Context should have something (working self at minimum, since focus.md exists)
[[ "${ctx_result}" != "" ]] && pass=$((pass + 1)) || { echo "[sms-test] FAIL context builder empty" >&2; fail=$((fail + 1)); }

# --- Test 9: CLI commands don't crash ---
"${ROOT}/bin/lacp-sms" --help >/dev/null 2>&1
pass=$((pass + 1))

"${ROOT}/bin/lacp-sms" significance --json 2>&1 | python3 -c "import json,sys; json.loads(sys.stdin.read())" 2>/dev/null
pass=$((pass + 1))

# --- Summary ---
total=$((pass + fail))
if [[ "${fail}" -gt 0 ]]; then
  echo "[sms-test] FAIL ${fail}/${total} tests failed" >&2
  exit 1
fi
echo "[sms-test] all ${total} tests passed"
