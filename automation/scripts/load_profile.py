#!/usr/bin/env python3
"""LACP Profile Loader — load and merge profile configuration.

Loads from (in priority order):
1. ~/.lacp/profile.yaml (user override)
2. <LACP_ROOT>/config/profiles/default.yaml (shipped default)

Usage:
    from load_profile import load_profile
    profile = load_profile()
    print(profile["identity"]["name"])

CLI:
    python3 load_profile.py              # print active profile as JSON
    python3 load_profile.py --yaml       # print as YAML
    python3 load_profile.py --get identity.name  # get specific key
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

LACP_ROOT = Path(os.environ.get("LACP_ROOT", str(Path(__file__).resolve().parent.parent)))
DEFAULT_PROFILE = LACP_ROOT / "config" / "profiles" / "default.yaml"
USER_PROFILE = Path.home() / ".lacp" / "profile.yaml"

DEFAULTS: dict[str, Any] = {
    "identity": {
        "name": "LACP",
        "tagline": "Local Agent Control Plane",
        "emoji": "⚡",
    },
    "banner": {
        "style": "box",
        "color": "cyan",
    },
    "defaults": {
        "agent": "",
        "model": "",
        "mode": "",
    },
    "session": {
        "greeting": "",
        "budget_tokens": 1500,
    },
    "focus": {
        "auto_inject": True,
        "stale_warn_days": 7,
        "show_in_banner": True,
    },
}


def _parse_yaml_simple(text: str) -> dict[str, Any]:
    """Minimal YAML parser for flat/nested key-value profiles.

    Handles:
    - key: value
    - key: "quoted value"
    - nested sections (2-space indent)
    - comments (#)
    - booleans (true/false)
    - integers
    """
    result: dict[str, Any] = {}
    current_section = ""

    for line in text.splitlines():
        stripped = line.split("#")[0].rstrip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            key = stripped.split(":")[0].strip()
            value = stripped.split(":", 1)[1].strip()
            if not value:
                current_section = key
                if key not in result:
                    result[key] = {}
            else:
                result[key] = _parse_value(value)
        elif indent >= 2 and current_section and ":" in stripped:
            key = stripped.split(":")[0].strip()
            value = stripped.split(":", 1)[1].strip()
            if isinstance(result.get(current_section), dict):
                result[current_section][key] = _parse_value(value)

    return result


def _parse_value(v: str) -> Any:
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v == "":
        return ""
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, recursing into dicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_profile() -> dict[str, Any]:
    """Load the active profile with defaults."""
    profile = dict(DEFAULTS)

    # Load shipped default
    if DEFAULT_PROFILE.exists():
        try:
            text = DEFAULT_PROFILE.read_text(encoding="utf-8")
            parsed = _parse_yaml_simple(text)
            profile = _deep_merge(profile, parsed)
        except Exception:
            pass

    # Load user override
    if USER_PROFILE.exists():
        try:
            text = USER_PROFILE.read_text(encoding="utf-8")
            parsed = _parse_yaml_simple(text)
            profile = _deep_merge(profile, parsed)
        except Exception:
            pass

    # Env var overrides (highest priority)
    env_agent = os.environ.get("LACP_DEFAULT_AGENT", "")
    env_model = os.environ.get("LACP_DEFAULT_MODEL", "")
    if env_agent:
        profile["defaults"]["agent"] = env_agent
    if env_model:
        profile["defaults"]["model"] = env_model

    return profile


def get_nested(profile: dict, dotpath: str) -> Any:
    """Get a nested value by dot path: 'identity.name' -> profile['identity']['name']."""
    keys = dotpath.split(".")
    current: Any = profile
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="LACP Profile Loader")
    parser.add_argument("--get", type=str, default="", help="Get specific key (dot path)")
    parser.add_argument("--yaml", action="store_true", help="Output as YAML-like format")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        profile = load_profile()
        assert profile["identity"]["name"] == "LACP"
        assert isinstance(profile["session"]["budget_tokens"], int)
        assert get_nested(profile, "identity.emoji") == "⚡"
        assert get_nested(profile, "nonexistent.key") is None
        print("self-test passed")
        return 0

    profile = load_profile()

    if args.get:
        value = get_nested(profile, args.get)
        if value is None:
            return 1
        print(value)
        return 0

    if args.yaml:
        for section, values in profile.items():
            print(f"{section}:")
            if isinstance(values, dict):
                for k, v in values.items():
                    print(f"  {k}: {v}")
            else:
                print(f"  {values}")
        return 0

    print(json.dumps(profile, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
