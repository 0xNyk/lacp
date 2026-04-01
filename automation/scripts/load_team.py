#!/usr/bin/env python3
"""LACP Team Loader — parse team YAML configs for lacp-up.

Loads team definitions from config/teams/ or a custom path.

Usage:
    from load_team import load_team
    team = load_team("default")  # loads config/teams/default.yaml

CLI:
    python3 load_team.py default              # print team as JSON
    python3 load_team.py /path/to/team.yaml   # load custom team file
    python3 load_team.py --list               # list available teams
    python3 load_team.py --self-test
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Reuse the simple YAML parser from load_profile
sys.path.insert(0, str(Path(__file__).parent))

LACP_ROOT = Path(os.environ.get("LACP_ROOT", str(Path(__file__).resolve().parent.parent)))
TEAMS_DIR = LACP_ROOT / "config" / "teams"


def _parse_team_yaml(text: str) -> dict[str, Any]:
    """Parse team YAML with role list support."""
    result: dict[str, Any] = {"name": "", "description": "", "roles": []}
    current_role: dict[str, Any] | None = None

    for line in text.splitlines():
        stripped = line.split("#")[0].rstrip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            key = stripped.split(":")[0].strip()
            value = stripped.split(":", 1)[1].strip()
            if key in ("name", "description"):
                result[key] = value.strip('"').strip("'")

        elif indent == 2 and stripped.strip().startswith("- name:"):
            # New role
            if current_role:
                result["roles"].append(current_role)
            name_val = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            current_role = {"name": name_val, "agent": "claude", "model": "", "purpose": "", "count": 1}

        elif indent == 4 and current_role and ":" in stripped:
            key = stripped.split(":")[0].strip()
            value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            if key == "count":
                try:
                    current_role[key] = int(value)
                except ValueError:
                    current_role[key] = 1
            elif key in ("agent", "model", "purpose", "name"):
                current_role[key] = value

    if current_role:
        result["roles"].append(current_role)

    return result


def load_team(name_or_path: str) -> dict[str, Any]:
    """Load a team config by name or file path."""
    path = Path(name_or_path)

    # Direct path
    if path.exists() and path.suffix in (".yaml", ".yml"):
        text = path.read_text(encoding="utf-8")
        return _parse_team_yaml(text)

    # Named team from config/teams/
    team_file = TEAMS_DIR / f"{name_or_path}.yaml"
    if team_file.exists():
        text = team_file.read_text(encoding="utf-8")
        return _parse_team_yaml(text)

    # Try .yml
    team_file = TEAMS_DIR / f"{name_or_path}.yml"
    if team_file.exists():
        text = team_file.read_text(encoding="utf-8")
        return _parse_team_yaml(text)

    return {"error": f"Team not found: {name_or_path}", "searched": [str(TEAMS_DIR)]}


def list_teams() -> list[dict[str, str]]:
    """List all available team configs."""
    teams = []
    if TEAMS_DIR.exists():
        for f in sorted(TEAMS_DIR.glob("*.yaml")) + sorted(TEAMS_DIR.glob("*.yml")):
            try:
                team = _parse_team_yaml(f.read_text(encoding="utf-8"))
                teams.append({
                    "name": team.get("name", f.stem),
                    "file": str(f),
                    "description": team.get("description", ""),
                    "roles": len(team.get("roles", [])),
                })
            except Exception:
                teams.append({"name": f.stem, "file": str(f), "description": "(parse error)", "roles": 0})
    return teams


def total_instances(team: dict[str, Any]) -> int:
    """Total number of instances this team needs."""
    return sum(r.get("count", 1) for r in team.get("roles", []))


def _self_test() -> None:
    teams = list_teams()
    assert len(teams) >= 1, f"Expected at least 1 team, got {len(teams)}"

    default = load_team("default")
    assert default.get("name") == "default", f"Expected 'default', got {default.get('name')}"
    assert len(default.get("roles", [])) >= 2, f"Expected 2+ roles, got {len(default.get('roles', []))}"
    assert default["roles"][0]["agent"] == "claude"
    assert total_instances(default) >= 2

    hetero = load_team("heterogeneous")
    assert len(hetero.get("roles", [])) == 3
    agents = [r["agent"] for r in hetero["roles"]]
    assert "claude" in agents and "codex" in agents

    # Test not-found
    missing = load_team("nonexistent-team")
    assert "error" in missing


def main() -> int:
    if "--self-test" in sys.argv:
        _self_test()
        print("self-test passed")
        return 0

    if "--list" in sys.argv:
        teams = list_teams()
        for t in teams:
            print(f"  {t['name']:20s} {t['roles']} roles  {t['description']}")
        return 0

    if len(sys.argv) < 2:
        print("Usage: load_team.py <name|path> | --list | --self-test", file=sys.stderr)
        return 1

    team = load_team(sys.argv[1])
    print(json.dumps(team, indent=2))
    return 0 if "error" not in team else 1


if __name__ == "__main__":
    raise SystemExit(main())
