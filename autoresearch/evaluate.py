#!/usr/bin/env python3
"""
LACP Brain Evaluation Harness (DO NOT MODIFY)

This is the fixed evaluation script for the autoresearch ratchet loop.
It runs all LACP diagnostic tools and computes a unified brain health score.

Metrics:
  1. Brain Health   — lacp-brain-doctor (vault symlinks, QMD, MCP, daily notes, etc.)
  2. System Health  — lacp-doctor (policy, hooks, paths, sandbox config)
  3. Knowledge Health — lacp-knowledge-doctor (graph integrity, orphans, contradictions)

Composite Score = weighted sum, normalized to 0-100 (higher is better).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

LACP_ROOT = Path.home() / "control" / "frameworks" / "lacp"
RESULTS_FILE = Path(__file__).parent / "results.tsv"

# Weights for composite score
WEIGHTS = {
    "brain": 0.40,    # Vault ecosystem health
    "system": 0.35,   # LACP control plane health
    "knowledge": 0.25, # Knowledge graph quality
}


def run_doctor(cmd: list[str], name: str) -> dict:
    """Run a doctor command and return parsed JSON output."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout)
        summary = data.get("summary", {})
        checks = data.get("checks", [])
        # Count from checks directly (more reliable than summary which varies per doctor)
        pass_count = sum(1 for c in checks if c.get("status") == "PASS")
        warn_count = sum(1 for c in checks if c.get("status") == "WARN")
        fail_count = sum(1 for c in checks if c.get("status") == "FAIL")
        return {
            "name": name,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": pass_count + warn_count + fail_count,
            "checks": checks,
            "ok": data.get("ok", False),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return {
            "name": name,
            "pass": 0, "warn": 0, "fail": 1, "total": 1,
            "checks": [],
            "ok": False,
            "error": str(e),
        }


def score_doctor(result: dict) -> float:
    """Score a doctor result as 0-100.

    pass = 1.0 points, warn = 0.5 points, fail = 0.0 points.
    Score = (earned / total) * 100
    """
    total = result["total"]
    if total == 0:
        return 0.0
    earned = result["pass"] * 1.0 + result["warn"] * 0.5 + result["fail"] * 0.0
    return (earned / total) * 100.0


def evaluate() -> dict:
    """Run all evaluations and return composite score."""
    start = time.time()

    bin_dir = LACP_ROOT / "bin"

    results = {
        "brain": run_doctor(
            [str(bin_dir / "lacp-brain-doctor"), "--json"], "brain"
        ),
        "system": run_doctor(
            [str(bin_dir / "lacp-doctor"), "--json"], "system"
        ),
        "knowledge": run_doctor(
            [str(bin_dir / "lacp-knowledge-doctor"), "--json"], "knowledge"
        ),
    }

    # Individual scores
    scores = {}
    for key, result in results.items():
        scores[key] = score_doctor(result)

    # Composite weighted score
    composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

    elapsed = time.time() - start

    evaluation = {
        "composite_score": round(composite, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "details": {
            k: {
                "pass": r["pass"],
                "warn": r["warn"],
                "fail": r["fail"],
                "total": r["total"],
            }
            for k, r in results.items()
        },
        "elapsed_seconds": round(elapsed, 1),
    }

    return evaluation


def print_summary(evaluation: dict) -> None:
    """Print evaluation summary in autoresearch-compatible format."""
    print("---")
    print(f"composite_score:  {evaluation['composite_score']:.4f}")
    for key, score in evaluation["scores"].items():
        detail = evaluation["details"][key]
        print(f"{key}_score:      {score:.4f}  ({detail['pass']}P/{detail['warn']}W/{detail['fail']}F)")
    print(f"eval_seconds:     {evaluation['elapsed_seconds']}")
    print("---")


if __name__ == "__main__":
    evaluation = evaluate()
    print_summary(evaluation)

    # Also dump full JSON for programmatic use
    json_path = Path(__file__).parent / "last_eval.json"
    json_path.write_text(json.dumps(evaluation, indent=2))
