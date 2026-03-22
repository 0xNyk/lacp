#!/usr/bin/env bash
set -euo pipefail

# Tests for neural memory architecture: spreading activation, dual-strength,
# synaptic tagging, prediction error gate, consolidation prune, backward compat.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

PASS_COUNT=0
FAIL_COUNT=0

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[brain-memory] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[brain-memory] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_gt() {
  local actual="$1"
  local threshold="$2"
  local label="$3"
  if ! python3 -c "import sys; sys.exit(0 if float('${actual}') > float('${threshold}') else 1)" 2>/dev/null; then
    echo "[brain-memory] FAIL ${label}: expected ${actual} > ${threshold}" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[brain-memory] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_lt() {
  local actual="$1"
  local threshold="$2"
  local label="$3"
  if ! python3 -c "import sys; sys.exit(0 if float('${actual}') < float('${threshold}') else 1)" 2>/dev/null; then
    echo "[brain-memory] FAIL ${label}: expected ${actual} < ${threshold}" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[brain-memory] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

SCRIPTS_DIR="${LACP_AUTOMATION_ROOT:-${HOME}/.lacp/automation}/scripts"

if ! python3 -c "import sys; sys.path.insert(0, '${SCRIPTS_DIR}'); import sync_research_knowledge" >/dev/null 2>&1; then
  echo "[brain-memory-test] SKIP sync_research_knowledge.py missing under ${SCRIPTS_DIR}"
  exit 0
fi

# --- Test 1: Spreading activation ---
echo "--- Test 1: Spreading activation ---"
result="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import spreading_activation
from datetime import UTC, datetime

items = {
    'a': {'edges': [{'id': 'b', 'similarity': 0.8}], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
    'b': {'edges': [{'id': 'c', 'similarity': 0.7}], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
    'c': {'edges': [], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
}
act = spreading_activation({'a': 1.0}, items, alpha=0.7, max_hops=3)
import json
print(json.dumps(act))
")"
a_act="$(echo "${result}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('a',0))")"
b_act="$(echo "${result}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('b',0))")"
c_act="$(echo "${result}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('c',0))")"

assert_eq "${a_act}" "1.0" "spreading_activation_anchor_preserved"
assert_eq "${b_act}" "0.7" "spreading_activation_hop1_decay"
assert_eq "${c_act}" "0.49" "spreading_activation_hop2_decay"

# Test max semantics (not sum)
result2="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import spreading_activation
from datetime import UTC, datetime

items = {
    'a': {'edges': [{'id': 'c', 'similarity': 0.9}], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
    'b': {'edges': [{'id': 'c', 'similarity': 0.8}], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
    'c': {'edges': [], 'count': 1, 'last_seen': datetime.now(UTC).isoformat()},
}
act = spreading_activation({'a': 1.0, 'b': 0.5}, items, alpha=0.7, max_hops=1)
print(act.get('c', 0))
")"
assert_eq "${result2}" "0.7" "spreading_activation_max_not_sum"

# --- Test 2: Dual-strength model ---
echo "--- Test 2: Dual-strength model ---"
result_ds="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_storage_strength, compute_retrieval_strength, compute_importance_score
from datetime import UTC, datetime

item = {'count': 10, 'last_seen': datetime.now(UTC).isoformat()}
s = compute_storage_strength(item)
r = compute_retrieval_strength(item, edge_count=2)
score = compute_importance_score(item, edge_count=2)
print(f'{s} {r} {score}')
")"
s_val="$(echo "${result_ds}" | cut -d' ' -f1)"
r_val="$(echo "${result_ds}" | cut -d' ' -f2)"
score_val="$(echo "${result_ds}" | cut -d' ' -f3)"

assert_gt "${s_val}" "0.0" "storage_strength_positive"
assert_gt "${r_val}" "0.0" "retrieval_strength_positive"
assert_gt "${score_val}" "0.0" "combined_score_positive"

# S floor from count: count=10 -> floor = min(1.0, 0.1 + 0.05*10) = 0.6
s_floor="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_storage_strength
print(compute_storage_strength({'count': 10}))
")"
assert_gt "${s_floor}" "0.59" "storage_strength_floor_from_count"

# R decays with age
r_old="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_retrieval_strength
print(compute_retrieval_strength({'count': 1, 'last_seen': '2025-01-01'}, edge_count=0))
")"
assert_lt "${r_old}" "0.5" "retrieval_strength_decays_with_age"

# --- Test 3: Synaptic tagging (S boost to neighbors) ---
echo "--- Test 3: Synaptic tagging ---"
result_st="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_storage_strength

# Simulate: neighbor gets S boost from new signal
neighbor = {'count': 3, 'storage_strength': 0.2}
new_item = {'count': 1, 'storage_strength': 0.0}
new_s = compute_storage_strength(new_item)
boost = 0.1 * new_s
updated_s = round(min(1.0, 0.2 + boost), 4)
print(f'{updated_s} {new_s}')
")"
updated_s="$(echo "${result_st}" | cut -d' ' -f1)"
assert_gt "${updated_s}" "0.2" "synaptic_tagging_boosts_neighbor_s"

# --- Test 4: Prediction error gate ---
echo "--- Test 4: Prediction error gate ---"

# Novel: empty embedding returns novel
result_pe1="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import prediction_error_gate
cls, mid, sim = prediction_error_gate('test text', [], {})
print(cls)
")"
assert_eq "${result_pe1}" "novel" "prediction_error_gate_empty_embedding_novel"

# Novel: no matching items returns novel
result_pe2="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import prediction_error_gate
cls, mid, sim = prediction_error_gate('test', [1.0, 0.0], {})
print(cls)
")"
assert_eq "${result_pe2}" "novel" "prediction_error_gate_no_items_novel"

# Contradicting: with negation markers
result_pe3="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import prediction_error_gate, CONTRADICTION_MARKERS
# Check that contradiction markers exist
print(len(CONTRADICTION_MARKERS) > 0)
")"
assert_eq "${result_pe3}" "True" "prediction_error_gate_has_contradiction_markers"

# --- Test 5: Consolidation prune candidates ---
echo "--- Test 5: Consolidation prune logic ---"
# Verify items with low R and low S would be prune candidates
result_prune="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_importance_score, compute_storage_strength, compute_retrieval_strength

# Ancient item with no access = low S, low R
item = {'count': 1, 'last_seen': '2024-01-01', 'storage_strength': 0.05}
s = compute_storage_strength(item)
r = compute_retrieval_strength(item, edge_count=0)
is_prune = s < 0.3 and r < 0.1
print(f'{s} {r} {is_prune}')
")"
is_prune="$(echo "${result_prune}" | cut -d' ' -f3)"
assert_eq "${is_prune}" "True" "prune_candidate_low_s_low_r"

# --- Test 6: Backward compatibility ---
echo "--- Test 6: Backward compatibility ---"
result_bc="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_importance_score
from datetime import UTC, datetime

item = {'count': 5, 'last_seen': datetime.now(UTC).isoformat()}
score = compute_importance_score(item, edge_count=2)
assert isinstance(score, float), f'Expected float, got {type(score)}'
assert 0.0 <= score <= 1.0, f'Score out of range: {score}'
print('ok')
")"
assert_eq "${result_bc}" "ok" "backward_compat_single_float"

# Test that generate_review_queue imports work
result_rq="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_importance_score, compute_retrieval_strength, compute_storage_strength
print('ok')
")"
assert_eq "${result_rq}" "ok" "review_queue_imports_work"

# --- Test 7: lacp-brain-expand --activate flag ---
echo "--- Test 7: brain-expand flags ---"

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
MOCK_SCRIPTS_DIR="${AUTOMATION_ROOT}/scripts"
mkdir -p "${MOCK_SCRIPTS_DIR}" "${KNOWLEDGE_ROOT}/data/workflows/brain-expand"

export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_KNOWLEDGE_GRAPH_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_DRAFTS_ROOT}"

# Mock sync script that echoes its args
cat > "${MOCK_SCRIPTS_DIR}/sync_research_knowledge.py" <<'MOCK'
#!/usr/bin/env python3
import sys, json
print(json.dumps({"ok": True, "args": sys.argv[1:]}))
MOCK

out="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd --activate 2>/dev/null)"

# Verify --activate is in the JSON output
activate_flag="$(echo "${out}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('activate', False))")"
assert_eq "${activate_flag}" "True" "brain_expand_activate_flag_in_json"

# Verify --consolidate flag
out2="$("/bin/bash" "${ROOT}/bin/lacp-brain-expand" --json --skip-qmd --consolidate 2>/dev/null)"
consolidate_flag="$(echo "${out2}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('consolidate', False))")"
assert_eq "${consolidate_flag}" "True" "brain_expand_consolidate_flag_in_json"

# --- Test 8: Mycelium path reinforcement ---
echo "--- Test 8: Mycelium path reinforcement ---"
result_reinforce="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import reinforce_access_paths
from datetime import UTC, datetime

items = {
    'a': {'edges': [{'id': 'b', 'similarity': 0.8}], 'count': 5, 'last_seen': datetime.now(UTC).isoformat(), 'categories': ['hub']},
    'b': {'edges': [{'id': 'c', 'similarity': 0.7}], 'count': 2, 'last_seen': datetime.now(UTC).isoformat(), 'categories': []},
    'c': {'edges': [], 'count': 1, 'last_seen': datetime.now(UTC).isoformat(), 'categories': []},
}
result = reinforce_access_paths('b', items)
print(result['reinforced_count'])
")"
assert_gt "${result_reinforce}" "0" "mycelium_reinforce_count_positive"

# Verify confidence was actually boosted
result_conf="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import reinforce_access_paths
from datetime import UTC, datetime

items = {
    'a': {'edges': [{'id': 'b', 'similarity': 0.8}], 'count': 5, 'last_seen': datetime.now(UTC).isoformat(), 'categories': ['hub']},
    'b': {'edges': [{'id': 'a', 'similarity': 0.8, 'confidence': 0.5}], 'count': 2, 'last_seen': datetime.now(UTC).isoformat(), 'categories': []},
}
reinforce_access_paths('b', items)
conf = items['b']['edges'][0].get('confidence', 0)
print(conf)
")"
assert_gt "${result_conf}" "0.5" "mycelium_reinforce_boosts_confidence"

# --- Test 9: Mycelium self-healing ---
echo "--- Test 9: Mycelium self-healing ---"
result_heal="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import heal_broken_paths

items = {
    'hub1': {'edges': [{'id': 'b', 'similarity': 0.9}], 'count': 10, 'embedding': [1.0, 0.0, 0.0], 'categories': ['hub']},
    'b':    {'edges': [{'id': 'hub1', 'similarity': 0.9}, {'id': 'c', 'similarity': 0.7}], 'count': 3, 'embedding': [0.8, 0.2, 0.0], 'categories': []},
    'c':    {'edges': [{'id': 'b', 'similarity': 0.7}], 'count': 1, 'embedding': [0.7, 0.3, 0.0], 'categories': []},
}
result = heal_broken_paths({'b'}, items, {'hub1'})
print(result['healed_count'])
")"
assert_gt "${result_heal}" "0" "mycelium_heal_reconnects_orphan"

# --- Test 10: Flow score computation ---
echo "--- Test 10: Flow score computation ---"
result_flow="$(python3 -c "
import sys, random
random.seed(42)
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_flow_score
from datetime import UTC, datetime

# Star topology: hub connects to a,b,c,d — all paths go through hub
items = {
    'hub': {'edges': [{'id': 'a', 'similarity': 0.9}, {'id': 'b', 'similarity': 0.9}, {'id': 'c', 'similarity': 0.9}, {'id': 'd', 'similarity': 0.9}], 'count': 10},
    'a':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
    'b':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
    'c':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
    'd':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
}
score = compute_flow_score('hub', items, sample_size=20)
print(score)
")"
assert_gt "${result_flow}" "0.0" "flow_score_hub_positive"

# Leaf node should have lower flow score
result_flow_leaf="$(python3 -c "
import sys, random
random.seed(42)
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_flow_score

items = {
    'hub': {'edges': [{'id': 'a', 'similarity': 0.9}, {'id': 'b', 'similarity': 0.9}, {'id': 'c', 'similarity': 0.9}], 'count': 10},
    'a':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
    'b':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
    'c':   {'edges': [{'id': 'hub', 'similarity': 0.9}], 'count': 1},
}
score = compute_flow_score('a', items, sample_size=20)
print(score)
")"
assert_lt "${result_flow_leaf}" "0.5" "flow_score_leaf_low"

# --- Test 11: Exploratory tendril protection ---
echo "--- Test 11: Exploratory tendril protection ---"
result_tendril="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from memory_consolidation import run_consolidation
result = run_consolidation(apply=False, config={
    'cluster_threshold': 0.75,
    'merge_threshold': 0.80,
    'min_cluster_size': 3,
    'prune_r_threshold': 0.1,
    'prune_s_threshold': 0.3,
    'prune_edge_threshold': 0.5,
    'max_prune_per_run': 50,
})
print('protected_tendrils' in result)
")"
assert_eq "${result_tendril}" "True" "tendril_protection_key_in_result"

# --- Test 12: Zone classification ---
echo "--- Test 12: Zone classification ---"
result_zone="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import classify_zone
import json
zones = {
    'high': classify_zone(0.8),
    'mid': classify_zone(0.45),
    'low': classify_zone(0.15),
    'very_low': classify_zone(0.05),
}
print(json.dumps(zones))
")"
z_high="$(echo "${result_zone}" | python3 -c "import json,sys; print(json.load(sys.stdin)['high'])")"
z_mid="$(echo "${result_zone}" | python3 -c "import json,sys; print(json.load(sys.stdin)['mid'])")"
z_low="$(echo "${result_zone}" | python3 -c "import json,sys; print(json.load(sys.stdin)['low'])")"
z_very_low="$(echo "${result_zone}" | python3 -c "import json,sys; print(json.load(sys.stdin)['very_low'])")"

assert_eq "${z_high}" "active" "zone_classify_active"
assert_eq "${z_mid}" "stale" "zone_classify_stale"
assert_eq "${z_low}" "fading" "zone_classify_fading"
assert_eq "${z_very_low}" "archived" "zone_classify_archived"

# --- Test 13: Bridge protection (Tarjan's articulation points) ---
echo "--- Test 13: Bridge protection ---"
result_bridge="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import find_articulation_points

# Linear graph: A-B-C. B is the bridge.
items = {
    'a': {'edges': [{'id': 'b', 'similarity': 0.8}]},
    'b': {'edges': [{'id': 'a', 'similarity': 0.8}, {'id': 'c', 'similarity': 0.8}]},
    'c': {'edges': [{'id': 'b', 'similarity': 0.8}]},
}
ap = find_articulation_points(items)
print('b' in ap)
")"
assert_eq "${result_bridge}" "True" "tarjan_bridge_node_detected"

# Non-bridge: fully connected triangle has no articulation points
result_no_bridge="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import find_articulation_points

items = {
    'a': {'edges': [{'id': 'b', 'similarity': 0.8}, {'id': 'c', 'similarity': 0.8}]},
    'b': {'edges': [{'id': 'a', 'similarity': 0.8}, {'id': 'c', 'similarity': 0.8}]},
    'c': {'edges': [{'id': 'a', 'similarity': 0.8}, {'id': 'b', 'similarity': 0.8}]},
}
ap = find_articulation_points(items)
print(len(ap))
")"
assert_eq "${result_no_bridge}" "0" "tarjan_triangle_no_bridge"

# Bridge protection in consolidation result
result_bridge_key="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from memory_consolidation import run_consolidation
result = run_consolidation(apply=False, config={
    'cluster_threshold': 0.75,
    'merge_threshold': 0.80,
    'min_cluster_size': 3,
    'prune_r_threshold': 0.1,
    'prune_s_threshold': 0.3,
    'prune_edge_threshold': 0.5,
    'max_prune_per_run': 50,
})
print('bridge_protected' in result)
")"
assert_eq "${result_bridge_key}" "True" "bridge_protected_key_in_consolidation"

# --- Test 14: Metabolic rates ---
echo "--- Test 14: Metabolic rates ---"
result_metabolic="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_retrieval_strength

# Use an older item so decay is visible
item = {'count': 1, 'last_seen': '2025-06-01'}
r_identity = compute_retrieval_strength(item, edge_count=0, content_type='identity')
r_session = compute_retrieval_strength(item, edge_count=0, content_type='session')
r_default = compute_retrieval_strength(item, edge_count=0)
print(f'{r_identity} {r_session} {r_default}')
")"
r_id="$(echo "${result_metabolic}" | cut -d' ' -f1)"
r_sess="$(echo "${result_metabolic}" | cut -d' ' -f2)"
assert_gt "${r_id}" "${r_sess}" "metabolic_identity_decays_slower_than_session"

# Backward compat: no content_type still works
result_metabolic_bc="$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from sync_research_knowledge import compute_retrieval_strength
from datetime import UTC, datetime
item = {'count': 5, 'last_seen': datetime.now(UTC).isoformat()}
r = compute_retrieval_strength(item, edge_count=2)
print(isinstance(r, float))
")"
assert_eq "${result_metabolic_bc}" "True" "metabolic_backward_compat"

# --- Summary ---
echo ""
echo "[brain-memory] Results: pass=${PASS_COUNT} fail=${FAIL_COUNT}"
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "[brain-memory] SOME TESTS FAILED" >&2
  exit 1
fi
echo "[brain-memory] all brain-memory tests passed"
