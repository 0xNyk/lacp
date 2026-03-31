#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


VAULT = Path.home() / "obsidian" / "nyk"
OBSIDIAN = VAULT / ".obsidian"
GRAPH_JSON = OBSIDIAN / "graph.json"
APP_JSON = OBSIDIAN / "app.json"
EXT_JSON = OBSIDIAN / "plugins" / "extended-graph" / "data.json"

EXPECTED_SYMLINKS = {
    VAULT / "knowledge": Path.home() / "control" / "knowledge" / "knowledge-memory",
    VAULT / "automation-scripts": Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent))) / "scripts",
}

IGNORE_FILTERS = [
    "knowledge/data/",
    "knowledge/benchmarks/",
    "knowledge/launchd/",
    "sessions/raw/",
    "_generated/extractions/",
    "_generated/sessions/",
    "automation-scripts/__pycache__/",
    "automation-scripts/*.pyc",
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    changed: bool = False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _default_state_engine(ext_payload: dict[str, Any]) -> dict[str, Any]:
    states = ext_payload.get("states")
    if not isinstance(states, list):
        return {}
    for state in states:
        if not isinstance(state, dict):
            continue
        if state.get("id") == "default-vault" or state.get("name") == "Default state":
            eng = state.get("engineOptions")
            if isinstance(eng, dict):
                return eng
    return {}


def repair_graph_config(apply: bool) -> CheckResult:
    graph = _read_json(GRAPH_JSON)
    ext = _read_json(EXT_JSON)
    eng = _default_state_engine(ext)

    if not graph:
        return CheckResult("graph_config", False, f"missing/invalid {GRAPH_JSON}")
    if not eng:
        return CheckResult("graph_config", False, f"missing default state engine in {EXT_JSON}")

    desired_groups = eng.get("colorGroups")
    desired_search = eng.get("search")
    changed = False

    if isinstance(desired_groups, list):
        current_groups = graph.get("colorGroups")
        if not isinstance(current_groups, list) or len(current_groups) < len(desired_groups):
            graph["colorGroups"] = desired_groups
            changed = True

    if isinstance(desired_search, str):
        current_search = graph.get("search")
        if not isinstance(current_search, str) or not current_search.strip():
            graph["search"] = desired_search
            changed = True

    graph["collapse-color-groups"] = False

    if changed and apply:
        _write_json(GRAPH_JSON, graph)

    count = len(graph.get("colorGroups", [])) if isinstance(graph.get("colorGroups"), list) else 0
    status = count > 0
    return CheckResult("graph_config", status, f"color_groups={count}", changed=changed)


def repair_app_ignore_filters(apply: bool) -> CheckResult:
    app = _read_json(APP_JSON)
    if not app:
        app = {
            "promptDelete": False,
            "alwaysUpdateLinks": True,
            "useMarkdownLinks": False,
            "newLinkFormat": "shortest",
            "userIgnoreFilters": [],
        }
    current = app.get("userIgnoreFilters")
    if not isinstance(current, list):
        current = []
    merged = sorted(set(str(x) for x in current) | set(IGNORE_FILTERS))
    changed = merged != current
    app["userIgnoreFilters"] = merged
    if changed and apply:
        _write_json(APP_JSON, app)
    return CheckResult("app_ignore_filters", True, f"filters={len(merged)}", changed=changed)


def repair_symlinks(apply: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    for link, expected_target in EXPECTED_SYMLINKS.items():
        expected = str(expected_target)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            current = str(link.resolve())
            if current == expected:
                results.append(CheckResult(f"symlink:{link.name}", True, expected))
                continue
            if apply:
                link.unlink(missing_ok=True)
                link.symlink_to(expected_target)
            results.append(CheckResult(f"symlink:{link.name}", apply, f"{current} -> {expected}", changed=True))
            continue
        if link.exists():
            results.append(CheckResult(f"symlink:{link.name}", False, f"exists but not symlink: {link}"))
            continue
        if apply:
            link.symlink_to(expected_target)
        results.append(CheckResult(f"symlink:{link.name}", apply, expected, changed=True))
    return results


def run(apply: bool) -> dict[str, Any]:
    checks: list[CheckResult] = [
        repair_graph_config(apply),
        repair_app_ignore_filters(apply),
    ]
    checks.extend(repair_symlinks(apply))

    ok = all(c.ok for c in checks)
    changed = sum(1 for c in checks if c.changed)
    return {
        "ok": ok,
        "mode": "apply" if apply else "check",
        "changed": changed,
        "checks": [
            {"name": c.name, "ok": c.ok, "detail": c.detail, "changed": c.changed}
            for c in checks
        ],
    }


def _self_test() -> None:
    assert isinstance(run(apply=False), dict)
    assert "checks" in run(apply=False)
    print("self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Obsidian graph config stays healthy.")
    parser.add_argument("--apply", action="store_true", help="Apply repairs in-place.")
    parser.add_argument("--self-test", action="store_true", help="Run inline tests and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0

    result = run(apply=args.apply)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
