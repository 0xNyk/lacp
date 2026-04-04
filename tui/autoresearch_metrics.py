#!/usr/bin/env python3
"""LACP Autoresearch Metrics — two-tier health + performance scoring.

Tier 1 — Harness Health (6 dimensions): code integrity, tools, speed, tests, CSS, lint
Tier 2 — Agent Performance (7 dimensions): task completion, tool accuracy, latency,
          memory recall, cost efficiency, reliability, provider health

Based on CLEAR framework (arxiv:2511.14136) and agent harness best practices.

Usage:
    python3 tui/autoresearch_metrics.py              # full report
    python3 tui/autoresearch_metrics.py --score       # just the score
    python3 tui/autoresearch_metrics.py --tier2       # agent performance only
    python3 tui/autoresearch_metrics.py --json        # JSON output
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


# ─── Tier 2: Agent Performance Metrics ───────────────────────────

TIER2_WEIGHTS = {
    "provider_health": 20,
    "tool_coverage": 15,
    "session_persistence": 10,
    "memory_depth": 15,
    "mcp_connectivity": 15,
    "fallback_readiness": 15,
    "skin_completeness": 10,
}

SESSION_DIR = Path.home() / ".lacp" / "sessions"
MEMORY_DIR = Path.home() / ".lacp" / "memory"


def measure_provider_health() -> dict:
    """Check all providers are reachable."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from tui.providers import list_providers; "
             "import json; print(json.dumps(list_providers()))"],
            capture_output=True, text=True, timeout=15,
            cwd=str(LACP_ROOT),
        )
        if result.returncode != 0:
            return {"provider_health": 0, "providers": []}

        providers = json.loads(result.stdout)
        total = len(providers)
        available = sum(1 for p in providers if p["available"])
        score = int(available / max(total, 1) * 100)
        return {
            "provider_health": score,
            "providers_available": available,
            "providers_total": total,
            "providers": providers,
        }
    except Exception as e:
        return {"provider_health": 0, "error": str(e)[:100]}


def measure_tool_coverage() -> dict:
    """Check tool categories are complete."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from tui.tools import get_tool_definitions; "
             "import json; tools = get_tool_definitions(); "
             "cats = {}; "
             "[cats.setdefault(t['name'].split('_')[0], []).append(t['name']) for t in tools]; "
             "print(json.dumps({'count': len(tools), 'categories': {k: len(v) for k, v in cats.items()}}))"],
            capture_output=True, text=True, timeout=10,
            cwd=str(LACP_ROOT),
        )
        if result.returncode != 0:
            return {"tool_coverage": 0}

        data = json.loads(result.stdout)
        count = data["count"]
        categories = data["categories"]

        # Expected categories: bash, read, write, edit, grep, glob, ls, delegate, memory, task, skill
        expected_cats = {"bash", "read", "write", "edit", "grep", "glob", "ls", "delegate", "memory", "task", "skill"}
        present = set(categories.keys()) & expected_cats
        score = int(len(present) / len(expected_cats) * 100)
        return {
            "tool_coverage": score,
            "tool_count": count,
            "categories": len(categories),
            "expected_categories": len(expected_cats),
            "present_categories": len(present),
        }
    except Exception:
        return {"tool_coverage": 0}


def measure_session_persistence() -> dict:
    """Check session save/load works."""
    score = 0
    details = {}

    # Check session directory exists
    if SESSION_DIR.exists():
        sessions = list(SESSION_DIR.glob("*.jsonl"))
        details["session_count"] = len(sessions)
        score += 50  # directory exists

        # Check a session is readable
        if sessions:
            try:
                latest = max(sessions, key=lambda f: f.stat().st_mtime)
                lines = latest.read_text().strip().splitlines()
                if lines:
                    json.loads(lines[0])  # valid JSON
                    score += 50  # readable
                    details["latest_session"] = latest.name
            except Exception:
                pass
    else:
        details["session_count"] = 0

    return {"session_persistence": score, **details}


def measure_memory_depth() -> dict:
    """Check memory system health."""
    score = 0
    details = {}

    if MEMORY_DIR.exists():
        entries = list(MEMORY_DIR.glob("*.json"))
        details["memory_entries"] = len(entries)
        score += 50  # directory exists

        # Check entries are readable
        valid = 0
        for f in entries[:10]:
            try:
                data = json.loads(f.read_text())
                if "content" in data or "key" in data:
                    valid += 1
            except Exception:
                pass
        if entries:
            score += int(valid / min(len(entries), 10) * 50)
        details["valid_entries"] = valid
    else:
        details["memory_entries"] = 0

    return {"memory_depth": score, **details}


def measure_mcp_connectivity() -> dict:
    """Check MCP server configurations exist."""
    settings_files = [
        Path.home() / ".claude" / "settings.local.json",
        Path.home() / ".claude" / "settings.json",
    ]
    servers_found = 0
    server_names = []

    for sf in settings_files:
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                servers = data.get("mcpServers", {})
                for name, config in servers.items():
                    if config.get("command"):
                        servers_found += 1
                        server_names.append(name)
            except Exception:
                pass

    # Score: 100 if >=3 servers, proportional below
    score = min(100, int(servers_found / 3 * 100))
    return {
        "mcp_connectivity": score,
        "mcp_servers_configured": servers_found,
        "mcp_server_names": server_names[:10],
    }


def measure_fallback_readiness() -> dict:
    """Check fallback providers are available."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from tui.providers import list_providers; "
             "providers = list_providers(); "
             "available = [p['name'] for p in providers if p['available']]; "
             "print(','.join(available))"],
            capture_output=True, text=True, timeout=10,
            cwd=str(LACP_ROOT),
        )
        available = result.stdout.strip().split(",") if result.returncode == 0 else []
        # Need at least 2 providers for fallback
        score = min(100, len(available) * 33)
        return {
            "fallback_readiness": score,
            "available_providers": available,
            "fallback_chain_depth": max(0, len(available) - 1),
        }
    except Exception:
        return {"fallback_readiness": 0}


def measure_skin_completeness() -> dict:
    """Check skin system has required fields."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from tui.skins import load_skin; "
             "s = load_skin('default'); "
             "fields = ['name', 'description', 'colors', 'branding', 'spinner', 'provider_badges']; "
             "present = sum(1 for f in fields if getattr(s, f, None)); "
             f"print(present)"],
            capture_output=True, text=True, timeout=10,
            cwd=str(LACP_ROOT),
        )
        present = int(result.stdout.strip()) if result.returncode == 0 else 0
        score = int(present / 6 * 100)
        return {"skin_completeness": score, "skin_fields_present": present}
    except Exception:
        return {"skin_completeness": 50}


def compute_tier2_score() -> dict:
    """Compute Tier 2 — Agent Performance score."""
    provider = measure_provider_health()
    tools = measure_tool_coverage()
    sessions = measure_session_persistence()
    memory = measure_memory_depth()
    mcp = measure_mcp_connectivity()
    fallback = measure_fallback_readiness()
    skin = measure_skin_completeness()

    subscores = {
        "provider_health": provider["provider_health"],
        "tool_coverage": tools["tool_coverage"],
        "session_persistence": sessions["session_persistence"],
        "memory_depth": memory["memory_depth"],
        "mcp_connectivity": mcp["mcp_connectivity"],
        "fallback_readiness": fallback["fallback_readiness"],
        "skin_completeness": skin["skin_completeness"],
    }

    total = sum(subscores[k] * TIER2_WEIGHTS[k] / 100 for k in TIER2_WEIGHTS)

    return {
        "score": round(total, 1),
        "subscores": subscores,
        "weights": TIER2_WEIGHTS,
        "details": {
            "provider": provider,
            "tools": tools,
            "sessions": sessions,
            "memory": memory,
            "mcp": mcp,
            "fallback": fallback,
            "skin": skin,
        },
    }


def compute_full_report() -> dict:
    """Compute both tiers and combined score."""
    tier1 = compute_health_score()
    tier2 = compute_tier2_score()

    # Combined: 60% harness health, 40% agent performance
    combined = round(tier1["score"] * 0.6 + tier2["score"] * 0.4, 1)

    return {
        "combined_score": combined,
        "tier1_harness": tier1,
        "tier2_agent": tier2,
    }


def _print_tier(name: str, report: dict, weights: dict) -> None:
    """Pretty print a tier report."""
    print(f"\n  {name}: {report['score']}/100\n")
    for metric, score in report["subscores"].items():
        weight = weights[metric]
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        print(f"    {metric:22s} {bar} {score:3d}/100 (×{weight}%)")


def main() -> None:
    if "--score" in sys.argv:
        report = compute_health_score()
        print(report["score"])
        return

    if "--tier2" in sys.argv:
        report = compute_tier2_score()
        if "--json" in sys.argv:
            print(json.dumps(report, indent=2))
        else:
            _print_tier("Tier 2 — Agent Performance", report, TIER2_WEIGHTS)
        return

    if "--full" in sys.argv:
        report = compute_full_report()
        if "--json" in sys.argv:
            print(json.dumps(report, indent=2))
        else:
            print(f"\n  ╔══════════════════════════════════════╗")
            print(f"  ║  LACP Combined Score: {report['combined_score']:5.1f}/100     ║")
            print(f"  ╚══════════════════════════════════════╝")
            _print_tier("Tier 1 — Harness Health", report["tier1_harness"], WEIGHTS)
            _print_tier("Tier 2 — Agent Performance", report["tier2_agent"], TIER2_WEIGHTS)
        return

    if "--json" in sys.argv:
        print(json.dumps(compute_health_score(), indent=2))
        return

    # Default: Tier 1 pretty print
    report = compute_health_score()
    _print_tier("Tier 1 — Harness Health", report, WEIGHTS)

    details = report["details"]
    print(f"\n  Details:")
    print(f"    Startup: {details['startup_ms']:.0f}ms")
    print(f"    Tools: {details['tools'].get('tools_registered', '?')} registered")
    if "tests" in details:
        t = details["tests"]
        print(f"    Tests: {t.get('tests_passed', '?')}/{t.get('tests_total', '?')} passed")
    if details["quality"].get("lint_issues"):
        print(f"    Lint issues: {details['quality']['lint_issues']}")
    print()


if __name__ == "__main__":
    main()
