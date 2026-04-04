#!/usr/bin/env python3
"""LACP Autoresearch Metrics — health score computation.

Measures LACP TUI health across 6 dimensions, outputs JSON report.
Used by the autoresearch agent to evaluate experiments.

Usage:
    python3 tui/autoresearch_metrics.py           # full report
    python3 tui/autoresearch_metrics.py --score    # just the score
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

LACP_ROOT = Path(__file__).parent.parent
TUI_DIR = LACP_ROOT / "tui"

# Metric weights (must sum to 100)
WEIGHTS = {
    "import_ok": 25,
    "tool_count": 15,
    "startup_ms": 15,
    "test_pass": 20,
    "css_valid": 10,
    "code_quality": 15,
}

# Baselines/targets
TOOL_COUNT_TARGET = 17
STARTUP_MS_TARGET = 500  # ms — faster = better
STARTUP_MS_MAX = 3000    # ms — beyond this = 0 score


def measure_import() -> dict:
    """Test if LACP REPL imports successfully."""
    try:
        start = time.time()
        result = subprocess.run(
            [sys.executable, "-c", "from tui.repl import LACPRepl; print('OK')"],
            capture_output=True, text=True, timeout=15,
            cwd=str(LACP_ROOT),
        )
        elapsed_ms = (time.time() - start) * 1000
        ok = result.returncode == 0 and "OK" in result.stdout
        return {
            "import_ok": 100 if ok else 0,
            "startup_ms": elapsed_ms,
            "import_error": result.stderr[:200] if not ok else "",
        }
    except Exception as e:
        return {"import_ok": 0, "startup_ms": 9999, "import_error": str(e)[:200]}


def measure_tools() -> dict:
    """Count registered tools."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from tui.tools import get_tool_definitions; "
             "tools = get_tool_definitions(); "
             f"print(len(tools))"],
            capture_output=True, text=True, timeout=10,
            cwd=str(LACP_ROOT),
        )
        count = int(result.stdout.strip()) if result.returncode == 0 else 0
        # Score: 100 if >= target, proportional below
        score = min(100, int(count / TOOL_COUNT_TARGET * 100))
        return {"tool_count": score, "tools_registered": count}
    except Exception:
        return {"tool_count": 0, "tools_registered": 0}


def measure_startup_time(elapsed_ms: float) -> int:
    """Score startup time (from import measurement)."""
    if elapsed_ms <= STARTUP_MS_TARGET:
        return 100
    if elapsed_ms >= STARTUP_MS_MAX:
        return 0
    # Linear interpolation
    return int(100 * (STARTUP_MS_MAX - elapsed_ms) / (STARTUP_MS_MAX - STARTUP_MS_TARGET))


def measure_tests() -> dict:
    """Run quick test suite."""
    test_script = LACP_ROOT / "bin" / "lacp-test"
    if not test_script.exists():
        return {"test_pass": 50, "tests_detail": "test script not found"}

    try:
        result = subprocess.run(
            ["bash", str(test_script), "--quick"],
            capture_output=True, text=True, timeout=60,
            cwd=str(LACP_ROOT),
        )
        output = result.stdout + result.stderr

        # Count PASS/FAIL lines
        passes = output.count("PASS")
        fails = output.count("FAIL")
        total = passes + fails
        if total == 0:
            return {"test_pass": 50, "tests_detail": "no test results parsed"}

        score = int(passes / total * 100)
        return {"test_pass": score, "tests_passed": passes, "tests_failed": fails, "tests_total": total}
    except subprocess.TimeoutExpired:
        return {"test_pass": 30, "tests_detail": "timeout"}
    except Exception as e:
        return {"test_pass": 0, "tests_detail": str(e)[:100]}


def measure_css_validity() -> dict:
    """Check if CSS in repl.py parses without obvious errors."""
    try:
        repl_file = TUI_DIR / "repl.py"
        content = repl_file.read_text()

        # Extract CSS string
        css_start = content.find('CSS = """')
        css_end = content.find('"""', css_start + 8)
        if css_start < 0 or css_end < 0:
            return {"css_valid": 50, "css_detail": "CSS block not found"}

        css_text = content[css_start + 8:css_end]

        # Basic validation: check balanced braces
        open_braces = css_text.count("{")
        close_braces = css_text.count("}")
        if open_braces != close_braces:
            return {"css_valid": 30, "css_detail": f"unbalanced braces: {open_braces} open, {close_braces} close"}

        # Check for common errors
        errors = []
        for i, line in enumerate(css_text.splitlines(), 1):
            stripped = line.strip()
            if stripped and not stripped.startswith((".", "#", "/", "*", "}")) and ":" in stripped:
                # Property line — should end with ;
                if not stripped.endswith((";", "{", "}")) and "{" not in stripped:
                    errors.append(f"line {i}: missing semicolon: {stripped[:40]}")

        if errors:
            return {"css_valid": max(20, 100 - len(errors) * 10), "css_errors": errors[:5]}

        return {"css_valid": 100, "css_detail": "ok"}
    except Exception as e:
        return {"css_valid": 0, "css_detail": str(e)[:100]}


def measure_code_quality() -> dict:
    """Run ruff linter on tui/ files."""
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "E,F,W", "--statistics", str(TUI_DIR)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return {"code_quality": 100, "lint_detail": "clean"}

        # Count issues
        lines = result.stdout.strip().splitlines()
        issue_count = len(lines)
        # Deduct 5 points per issue, min 0
        score = max(0, 100 - issue_count * 5)
        return {"code_quality": score, "lint_issues": issue_count, "lint_detail": result.stdout[:300]}
    except FileNotFoundError:
        # ruff not installed — give neutral score
        return {"code_quality": 70, "lint_detail": "ruff not found"}
    except Exception as e:
        return {"code_quality": 50, "lint_detail": str(e)[:100]}


def compute_health_score() -> dict:
    """Compute full health report with weighted score."""
    # Run measurements
    import_result = measure_import()
    tools_result = measure_tools()
    startup_score = measure_startup_time(import_result["startup_ms"])
    tests_result = measure_tests()
    css_result = measure_css_validity()
    quality_result = measure_code_quality()

    # Subscores
    subscores = {
        "import_ok": import_result["import_ok"],
        "tool_count": tools_result["tool_count"],
        "startup_ms": startup_score,
        "test_pass": tests_result["test_pass"],
        "css_valid": css_result["css_valid"],
        "code_quality": quality_result["code_quality"],
    }

    # Weighted total
    total_score = sum(subscores[k] * WEIGHTS[k] / 100 for k in WEIGHTS)

    return {
        "score": round(total_score, 1),
        "subscores": subscores,
        "weights": WEIGHTS,
        "details": {
            "import": import_result,
            "tools": tools_result,
            "startup_ms": round(import_result["startup_ms"], 0),
            "tests": tests_result,
            "css": css_result,
            "quality": quality_result,
        },
    }


def main() -> None:
    report = compute_health_score()

    if "--score" in sys.argv:
        print(report["score"])
        return

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
        return

    # Pretty print
    print(f"\n  LACP Health Score: {report['score']}/100\n")
    print("  Subscores:")
    for metric, score in report["subscores"].items():
        weight = WEIGHTS[metric]
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        print(f"    {metric:15s} {bar} {score:3d}/100 (×{weight}%)")

    print(f"\n  Details:")
    details = report["details"]
    print(f"    Startup: {details['startup_ms']:.0f}ms")
    print(f"    Tools: {details['tools'].get('tools_registered', '?')} registered")
    if "tests" in details:
        t = details["tests"]
        print(f"    Tests: {t.get('tests_passed', '?')}/{t.get('tests_total', '?')} passed")
    if details["css"].get("css_errors"):
        print(f"    CSS errors: {details['css']['css_errors'][:3]}")
    if details["quality"].get("lint_issues"):
        print(f"    Lint issues: {details['quality']['lint_issues']}")
    print()


if __name__ == "__main__":
    main()
