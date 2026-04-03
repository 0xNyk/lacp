"""LACP Skin Engine — data-driven CLI visual customization.

Skins are YAML files that define colors, branding, spinners, and ASCII art.
Compatible with hermes-agent skin format.

Usage:
    from skins import load_skin, list_skins

    skin = load_skin("default")
    print(skin.branding["welcome"])
    print(skin.color("banner_title"))
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "automation" / "scripts"))

LACP_ROOT = Path(__file__).parent.parent
BUILTIN_SKINS = LACP_ROOT / "config" / "skins"
USER_SKINS = Path.home() / ".lacp" / "skins"

DEFAULTS = {
    "name": "default",
    "description": "",
    "colors": {
        "banner_border": "#00d4ff",
        "banner_title": "#ffffff",
        "banner_accent": "#00aaff",
        "banner_dim": "#555566",
        "status_bg": "#16213e",
        "status_text": "#00d4ff",
        "status_accent": "#ffffff",
        "user_label": "#00d4ff",
        "assistant_label": "#aa88ff",
        "assistant_border": "#333366",
        "prompt_border": "#00aaff",
        "system_text": "#666688",
        "ok": "#4caf50",
        "error": "#ef5350",
        "warn": "#ffa726",
    },
    "branding": {
        "agent_name": "LACP",
        "tagline": "Local Agent Control Plane",
        "welcome": "Control Plane active.",
        "prompt_symbol": "⚡ ❯ ",
        "response_label": " ⚡ LACP ",
        "goodbye": "Session complete.",
        "help_header": "⚡ Commands",
    },
    "spinner": {
        "thinking_faces": ["◐", "◓", "◑", "◒"],
        "thinking_verbs": ["reasoning", "analyzing", "synthesizing"],
        "wings": [["⟪⚡", "⚡⟫"]],
    },
    "provider_badges": {
        "anthropic": "[bold #a67df4]anthropic[/]",
        "openai": "[bold #4ade80]openai[/]",
        "ollama": "[bold #f97316]ollama[/]",
    },
    "banner_logo": "",
    "banner_hero": "",
}


def _parse_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML parser for skin files."""
    result: dict[str, Any] = {}
    current_section = ""
    current_list: list | None = None
    current_list_key = ""
    in_multiline = False
    multiline_key = ""
    multiline_lines: list[str] = []

    for raw_line in text.splitlines():
        # Handle multiline blocks (|)
        if in_multiline:
            if raw_line and (raw_line[0] == " " or raw_line.strip() == ""):
                multiline_lines.append(raw_line)
                continue
            else:
                # End of multiline block
                content = "\n".join(multiline_lines)
                if current_section and multiline_key:
                    if not isinstance(result.get(current_section), dict):
                        result[current_section] = {}
                    result[current_section][multiline_key] = content
                else:
                    result[multiline_key] = content
                in_multiline = False
                multiline_lines = []

        stripped = raw_line.split("#")[0].rstrip() if not raw_line.strip().startswith("#") else ""
        if raw_line.strip().startswith("#"):
            continue
        if not stripped:
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        # List items
        if stripped.strip().startswith("- "):
            val = stripped.strip()[2:].strip().strip('"').strip("'")
            if current_list is not None:
                # Nested list item
                if val.startswith("["):
                    # Inline list like ["a", "b"]
                    import json as _json
                    try:
                        current_list.append(_json.loads(val.replace("'", '"')))
                    except Exception:
                        current_list.append(val)
                else:
                    current_list.append(val)
                continue

        # End of list
        if current_list is not None and not stripped.strip().startswith("- "):
            if current_section:
                if not isinstance(result.get(current_section), dict):
                    result[current_section] = {}
                result[current_section][current_list_key] = current_list
            current_list = None
            current_list_key = ""

        if ":" in stripped:
            key = stripped.split(":")[0].strip()
            value = stripped.split(":", 1)[1].strip()

            # Multiline block
            if value == "|" or value == "|-":
                in_multiline = True
                multiline_key = key
                multiline_lines = []
                if indent == 0:
                    current_section = ""  # top-level multiline
                continue

            if indent == 0:
                if not value:
                    current_section = key
                    if key not in result:
                        result[key] = {}
                else:
                    result[key] = _parse_value(value)
                    current_section = ""
            elif indent >= 2 and current_section:
                if not value:
                    # Start of a list
                    current_list = []
                    current_list_key = key
                else:
                    if not isinstance(result.get(current_section), dict):
                        result[current_section] = {}
                    result[current_section][key] = _parse_value(value)

    # Flush remaining multiline or list
    if in_multiline and multiline_lines:
        content = "\n".join(multiline_lines)
        if current_section and multiline_key:
            if not isinstance(result.get(current_section), dict):
                result[current_section] = {}
            result[current_section][multiline_key] = content
        elif multiline_key:
            result[multiline_key] = content

    if current_list is not None:
        if current_section:
            if not isinstance(result.get(current_section), dict):
                result[current_section] = {}
            result[current_section][current_list_key] = current_list

    return result


def _parse_value(v: str) -> Any:
    v = v.strip()
    for q in ('"', "'"):
        if v.startswith(q) and v.endswith(q):
            return v[1:-1]
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    try:
        return int(v)
    except ValueError:
        pass
    return v


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class Skin:
    name: str
    description: str
    colors: dict[str, str]
    branding: dict[str, str]
    spinner: dict[str, Any]
    provider_badges: dict[str, str]
    banner_logo: str
    banner_hero: str
    raw: dict[str, Any] = field(default_factory=dict)

    def color(self, key: str) -> str:
        return self.colors.get(key, "#ffffff")

    def brand(self, key: str) -> str:
        return self.branding.get(key, "")

    def badge(self, provider: str) -> str:
        return self.provider_badges.get(provider, f"[bold]{provider}[/]")


def load_skin(name: str = "") -> Skin:
    """Load a skin by name. Checks user skins first, then built-in."""
    if not name:
        name = os.environ.get("LACP_SKIN", "default")

    # Check user skins
    for ext in (".yaml", ".yml"):
        user_path = USER_SKINS / f"{name}{ext}"
        if user_path.exists():
            raw = _parse_yaml(user_path.read_text(encoding="utf-8"))
            merged = _deep_merge(DEFAULTS, raw)
            return _skin_from_dict(merged)

    # Check built-in
    for ext in (".yaml", ".yml"):
        builtin_path = BUILTIN_SKINS / f"{name}{ext}"
        if builtin_path.exists():
            raw = _parse_yaml(builtin_path.read_text(encoding="utf-8"))
            merged = _deep_merge(DEFAULTS, raw)
            return _skin_from_dict(merged)

    # Fallback to defaults
    return _skin_from_dict(DEFAULTS)


def _skin_from_dict(d: dict) -> Skin:
    return Skin(
        name=d.get("name", "default"),
        description=d.get("description", ""),
        colors=d.get("colors", {}),
        branding=d.get("branding", {}),
        spinner=d.get("spinner", {}),
        provider_badges=d.get("provider_badges", {}),
        banner_logo=d.get("banner_logo", ""),
        banner_hero=d.get("banner_hero", ""),
        raw=d,
    )


def list_skins() -> list[dict[str, str]]:
    """List all available skins."""
    skins = []
    seen = set()

    for skin_dir in [USER_SKINS, BUILTIN_SKINS]:
        if not skin_dir.exists():
            continue
        for f in sorted(skin_dir.glob("*.yaml")) + sorted(skin_dir.glob("*.yml")):
            name = f.stem
            if name in seen:
                continue
            seen.add(name)
            try:
                raw = _parse_yaml(f.read_text(encoding="utf-8"))
                skins.append({
                    "name": name,
                    "description": raw.get("description", ""),
                    "source": "user" if skin_dir == USER_SKINS else "built-in",
                })
            except Exception:
                skins.append({"name": name, "description": "(parse error)", "source": str(skin_dir)})

    return skins
