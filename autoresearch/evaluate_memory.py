#!/usr/bin/env python3
"""
LACP Agent Memory Architecture Evaluator (DO NOT MODIFY)

Scores the quality of LACP's memory subsystem across 5 dimensions:

1. Code Quality     — shellcheck + test pass rate on memory-related code
2. Architecture     — separation of concerns, layer isolation, API surface
3. Retrieval        — embedding config, search quality, index freshness
4. Consolidation    — temporal decay, mycelium pruning, promotion pipeline
5. Multi-Agent      — sync mechanisms, conflict resolution, shared knowledge

Composite Score = weighted sum, normalized to 0-100 (higher is better).
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from collections import Counter

LACP_ROOT = Path.home() / "control" / "frameworks" / "lacp"
KNOWLEDGE_ROOT = Path(os.environ.get("LACP_KNOWLEDGE_ROOT",
    str(Path.home() / "control" / "knowledge" / "knowledge-memory")))

WEIGHTS = {
    "code_quality": 0.25,
    "architecture": 0.25,
    "retrieval": 0.20,
    "consolidation": 0.15,
    "multi_agent": 0.15,
}

MEMORY_SCRIPTS = [
    "bin/lacp-brain-doctor",
    "bin/lacp-brain-expand",
    "bin/lacp-brain-ingest",
    "bin/lacp-knowledge-doctor",
]

MEMORY_PYTHON = [
    "hooks/stop_quality_gate.py",
    "hooks/session_start.py",
    "hooks/detect_session_changes.py",
    "hooks/write_validate.py",
]

MEMORY_CONFIGS = ["config/obsidian/manifest.json"]

MEMORY_TESTS = [
    "scripts/ci/test-brain-doctor.sh",
    "scripts/ci/test-knowledge-doctor.sh",
    "scripts/ci/test-brain-expand.sh",
    "scripts/ci/test-brain-ingest.sh",
    "scripts/ci/test-brain-stack.sh",
]


def check_exists(files):
    exists = sum(1 for f in files if (LACP_ROOT / f).exists())
    return exists, len(files)


def run_shellcheck(files):
    existing = [str(LACP_ROOT / f) for f in files if (LACP_ROOT / f).exists()]
    if not existing:
        return 0, 0
    try:
        result = subprocess.run(
            ["shellcheck", "--severity=warning", "--format=json"] + existing,
            capture_output=True, text=True, timeout=30
        )
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        return len(issues), len(existing)
    except Exception:
        return 0, 0


def run_memory_tests():
    passed, total = 0, 0
    for test in MEMORY_TESTS:
        test_path = LACP_ROOT / test
        if not test_path.exists():
            continue
        total += 1
        try:
            result = subprocess.run(
                ["bash", str(test_path)],
                capture_output=True, text=True, timeout=60,
                env={**os.environ, "LACP_TEST_MODE": "1"}
            )
            if result.returncode == 0:
                passed += 1
        except subprocess.TimeoutExpired:
            pass
    return passed, total


def score_code_quality():
    checks = {}
    script_exists, script_total = check_exists(MEMORY_SCRIPTS)
    python_exists, python_total = check_exists(MEMORY_PYTHON)
    test_exists, test_total = check_exists(MEMORY_TESTS)
    config_exists, config_total = check_exists(MEMORY_CONFIGS)

    checks["scripts_exist"] = f"{script_exists}/{script_total}"
    checks["python_exist"] = f"{python_exists}/{python_total}"
    checks["tests_exist"] = f"{test_exists}/{test_total}"
    checks["configs_exist"] = f"{config_exists}/{config_total}"

    all_exist = script_exists + python_exists + test_exists + config_exists
    all_total = script_total + python_total + test_total + config_total
    existence_score = (all_exist / max(all_total, 1)) * 100

    warnings, checked = run_shellcheck(MEMORY_SCRIPTS)
    checks["shellcheck_warnings"] = warnings
    shellcheck_score = max(0, 100 - warnings * 10)

    passed, total = run_memory_tests()
    checks["tests_passed"] = f"{passed}/{total}"
    test_score = (passed / max(total, 1)) * 100

    score = existence_score * 0.3 + shellcheck_score * 0.3 + test_score * 0.4
    return score, checks


def score_architecture():
    checks = {}
    parts = []

    layers = {
        "session": (LACP_ROOT / "hooks" / "session_start.py").exists(),
        "knowledge": (LACP_ROOT / "bin" / "lacp-knowledge-doctor").exists(),
        "ingestion": (LACP_ROOT / "bin" / "lacp-brain-ingest").exists(),
        "expansion": (LACP_ROOT / "bin" / "lacp-brain-expand").exists(),
        "consolidation": (LACP_ROOT / "bin" / "lacp-brain-expand").exists(),
    }
    layer_count = sum(layers.values())
    checks["layers"] = f"{layer_count}/5"
    parts.append((layer_count / 5) * 100)

    has_stack = (LACP_ROOT / "bin" / "lacp-brain-stack").exists()
    checks["stack_init"] = "present" if has_stack else "missing"
    parts.append(100 if has_stack else 0)

    has_lib = (LACP_ROOT / "scripts" / "lacp-lib.sh").exists()
    checks["shared_lib"] = "present" if has_lib else "missing"
    parts.append(100 if has_lib else 0)

    policies = ["config/sandbox-policy.json", "config/obsidian/manifest.json"]
    pe, pt = check_exists(policies)
    checks["policies"] = f"{pe}/{pt}"
    parts.append((pe / max(pt, 1)) * 100)

    doctors = ["bin/lacp-doctor", "bin/lacp-brain-doctor", "bin/lacp-knowledge-doctor"]
    de, dt = check_exists(doctors)
    checks["doctors"] = f"{de}/{dt}"
    parts.append((de / max(dt, 1)) * 100)

    max_loc = 0
    for script in MEMORY_SCRIPTS:
        p = LACP_ROOT / script
        if p.exists():
            max_loc = max(max_loc, len(p.read_text().splitlines()))
    checks["max_loc"] = max_loc
    parts.append(100 if max_loc <= 500 else max(0, 100 - (max_loc - 500) * 0.1))

    return sum(parts) / len(parts), checks


def score_retrieval():
    checks = {}
    parts = []

    sc_dir = Path.home() / ".local" / "share" / "smart-connections-mcp"
    checks["embeddings"] = "present" if sc_dir.exists() else "missing"
    parts.append(100 if sc_dir.exists() else 0)

    qmd_available = False
    try:
        result = subprocess.run(["which", "qmd"], capture_output=True, timeout=5)
        qmd_available = result.returncode == 0
    except Exception:
        pass
    checks["qmd_search"] = "available" if qmd_available else "missing"
    parts.append(100 if qmd_available else 50)

    dirs = {"research": KNOWLEDGE_ROOT / "research",
            "memory": KNOWLEDGE_ROOT / "memory",
            "graph": KNOWLEDGE_ROOT / "graph"}
    present = sum(1 for d in dirs.values() if d.exists())
    checks["structure"] = f"{present}/{len(dirs)}"
    parts.append((present / len(dirs)) * 100)

    note_count = len(list(KNOWLEDGE_ROOT.rglob("*.md")))
    checks["notes"] = note_count
    parts.append(min(100, note_count / 10))

    return sum(parts) / len(parts), checks


def score_consolidation():
    checks = {}
    parts = []

    expand_path = LACP_ROOT / "bin" / "lacp-brain-expand"
    if expand_path.exists():
        content = expand_path.read_text().lower()
        features = {
            "fsrs": any(w in content for w in ["fsrs", "decay", "retrievability"]),
            "consolidation": "consolidat" in content,
            "gap_detection": "gap" in content,
            "activation": any(w in content for w in ["activation", "spreading"]),
            "pruning": any(w in content for w in ["prun", "tendril"]),
        }
        count = sum(features.values())
        checks["features"] = f"{count}/5"
        parts.append((count / 5) * 100)
    else:
        checks["features"] = "missing"
        parts.append(0)

    has_cron = False
    for plist in Path.home().glob("Library/LaunchAgents/*vault*"):
        has_cron = True
    checks["periodic"] = "configured" if has_cron else "missing"
    parts.append(100 if has_cron else 30)

    taxonomy = KNOWLEDGE_ROOT / "data" / "taxonomy.json"
    checks["taxonomy"] = "present" if taxonomy.exists() else "missing"
    parts.append(100 if taxonomy.exists() else 0)

    return sum(parts) / len(parts), checks


def score_multi_agent():
    checks = {}
    parts = []

    syncthing = False
    try:
        result = subprocess.run(["pgrep", "-x", "syncthing"], capture_output=True, timeout=5)
        syncthing = result.returncode == 0
    except Exception:
        pass
    checks["vault_sync"] = "running" if syncthing else "not running"
    parts.append(100 if syncthing else 0)

    vault = Path(os.environ.get("LACP_OBSIDIAN_VAULT", str(Path.home() / "obsidian" / "vault")))
    agents_dir = vault / "agents"
    if agents_dir.exists():
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        checks["agents"] = f"{len(agent_dirs)} agents"
        parts.append(min(100, len(agent_dirs) * 33))
    else:
        checks["agents"] = "missing"
        parts.append(0)

    has_bus = False
    try:
        result = subprocess.run(
            ["ssh", "jarv", "test -f /srv/hermes-bus/bus.py && echo yes"],
            capture_output=True, text=True, timeout=10
        )
        has_bus = "yes" in result.stdout
    except Exception:
        pass
    checks["inter_agent_bus"] = "yes" if has_bus else "no"
    parts.append(100 if has_bus else 0)

    checks["shared_read"] = "syncthing" if syncthing else "none"
    parts.append(100 if syncthing else 0)

    return sum(parts) / len(parts), checks


def run_evaluation():
    start = time.time()
    scorers = {
        "code_quality": score_code_quality,
        "architecture": score_architecture,
        "retrieval": score_retrieval,
        "consolidation": score_consolidation,
        "multi_agent": score_multi_agent,
    }

    scores = {}
    details = {}
    for key, scorer in scorers.items():
        score, checks = scorer()
        scores[key] = round(score, 4)
        details[key] = checks

    composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    elapsed = time.time() - start

    return {
        "composite_score": round(composite, 4),
        "scores": scores,
        "details": details,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    result = run_evaluation()
    print("---")
    print(f"composite_score:      {result['composite_score']:.4f}")
    for key, score in result["scores"].items():
        print(f"{key:22s} {score:.4f}")
    print(f"eval_seconds:         {result['elapsed_seconds']}")
    print("---")
    json_path = Path(__file__).parent / "last_eval_memory.json"
    json_path.write_text(json.dumps(result, indent=2))
