#!/usr/bin/env python3
"""
LACP Brain Optimizer — The editable file.

This script contains all tunable parameters and repair actions for the
LACP brain ecosystem. The autoresearch agent modifies THIS FILE to
improve the composite brain health score.

The agent can:
  - Fix broken symlinks
  - Adjust vault structure
  - Tune knowledge graph parameters
  - Fix config drift
  - Repair MCP server configurations
  - Optimize QMD collections
  - Tune memory consolidation parameters
  - Fix LACP policy configurations

The agent CANNOT:
  - Modify evaluate.py (the scoring harness)
  - Delete user content from the vault
  - Modify .env secrets or API keys
  - Change git history
"""

import json
import os
import subprocess
import sys
from pathlib import Path

LACP_ROOT = Path.home() / "control" / "frameworks" / "lacp"
VAULT_ROOT = Path(os.environ.get("LACP_OBSIDIAN_VAULT", str(Path.home() / "obsidian" / "nyk")))
KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"

# ============================================================================
# TUNABLE PARAMETERS — Agent modifies these
# ============================================================================

# Vault symlink targets (agent can fix broken symlinks)
SYMLINK_TARGETS = {
    "sessions": str(Path.home() / ".lacp" / "sessions"),
    "skills": str(Path.home() / ".lacp" / "skills"),
    "knowledge": str(KNOWLEDGE_ROOT),
    "docs": str(Path.home() / "docs"),
    "automation-scripts": str(LACP_ROOT / "automation" / "scripts"),
}

# Knowledge graph parameters
GRAPH_PARAMS = {
    "consolidation_similarity_threshold": 0.70,
    "temporal_decay_half_life_days": 30,
    "max_inbox_size": 200,
    "min_atlas_mocs": 7,
    "min_qmd_collections": 6,
    "embedding_model": "mxbai-embed-large",
    "embedding_dimensions": 1024,
}

# Memory consolidation tuning
MEMORY_PARAMS = {
    "session_flush_min_turns": 6,
    "memory_char_limit": 2200,
    "user_char_limit": 1375,
    "nudge_interval": 10,
    "spreading_activation_threshold": 0.55,
    "tendril_protection_enabled": True,
    "hub_detection_percentile": 90,
}

# MCP server expected configurations
MCP_SERVERS = {
    "memory": {"required": True},
    "smart-connections": {"required": True},
    "qmd": {"required": True},
}


# ============================================================================
# REPAIR ACTIONS — Agent can add/modify these
# ============================================================================

def fix_broken_symlinks():
    """Repair broken vault symlinks using configured targets."""
    fixed = 0
    for name, target in SYMLINK_TARGETS.items():
        link_path = VAULT_ROOT / name
        target_path = Path(target)

        if not target_path.exists():
            print(f"  SKIP {name}: target {target} does not exist")
            continue

        if link_path.is_symlink():
            current = os.readlink(str(link_path))
            if current != target and not link_path.exists():
                os.unlink(str(link_path))
                os.symlink(target, str(link_path))
                print(f"  FIXED {name}: {current} -> {target}")
                fixed += 1
            elif current != target:
                # Symlink works but points elsewhere
                print(f"  OK {name}: works (points to {current})")
            else:
                print(f"  OK {name}: correct")
        elif not link_path.exists():
            os.symlink(target, str(link_path))
            print(f"  CREATED {name} -> {target}")
            fixed += 1
        else:
            print(f"  SKIP {name}: exists as regular dir/file")

    return fixed


def ensure_daily_note():
    """Create today's daily note if missing."""
    from datetime import date
    daily_dir = VAULT_ROOT / "00-home" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    note_path = daily_dir / f"{today}.md"

    if not note_path.exists():
        note_path.write_text(
            f"---\ndate: {today}\ntags: [daily]\n---\n\n# {today}\n\n"
        )
        print(f"  CREATED daily note: {note_path.name}")
        return 1
    else:
        print(f"  OK daily note exists: {note_path.name}")
        return 0


def ensure_atlas_mocs():
    """Ensure minimum atlas MOC count."""
    atlas_dir = VAULT_ROOT / "atlas"
    if not atlas_dir.exists():
        atlas_dir.mkdir(parents=True, exist_ok=True)

    existing = list(atlas_dir.glob("*.md"))
    count = len(existing)
    target = GRAPH_PARAMS["min_atlas_mocs"]

    if count >= target:
        print(f"  OK atlas MOCs: {count}/{target}")
        return 0

    print(f"  WARN atlas MOCs: {count}/{target} (below minimum)")
    return 0  # Don't auto-create MOCs — they need human curation


def check_inbox_health():
    """Report inbox size relative to threshold."""
    inbox_dir = VAULT_ROOT / "inbox"
    if not inbox_dir.exists():
        print("  WARN inbox dir missing")
        return

    items = list(inbox_dir.iterdir())
    count = len([f for f in items if f.is_file() and f.suffix == ".md"])
    threshold = GRAPH_PARAMS["max_inbox_size"]

    if count > threshold:
        print(f"  WARN inbox: {count} items (threshold: {threshold})")
    else:
        print(f"  OK inbox: {count} items")


def fix_obsidian_config_drift():
    """Check and fix Obsidian config drift from LACP manifest."""
    manifest_path = LACP_ROOT / "config" / "obsidian" / "manifest.json"
    if not manifest_path.exists():
        print("  SKIP obsidian manifest not found")
        return 0

    # Run the obsidian audit command if available
    obsidian_cmd = LACP_ROOT / "bin" / "lacp-obsidian"
    if obsidian_cmd.exists():
        try:
            result = subprocess.run(
                [str(obsidian_cmd), "audit", "--json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print("  OK obsidian config in sync")
            else:
                print("  WARN obsidian config drift detected")
                # Could auto-apply: lacp-obsidian apply
            return 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    print("  SKIP obsidian audit not available")
    return 0


# ============================================================================
# MAIN OPTIMIZATION RUN
# ============================================================================

def optimize():
    """Run all optimization/repair actions."""
    print("=== LACP Brain Optimization Run ===\n")

    print("[1/5] Fixing broken symlinks...")
    fixes = fix_broken_symlinks()

    print("\n[2/5] Ensuring daily note...")
    fixes += ensure_daily_note()

    print("\n[3/5] Checking atlas MOCs...")
    ensure_atlas_mocs()

    print("\n[4/5] Checking inbox health...")
    check_inbox_health()

    print("\n[5/5] Checking Obsidian config drift...")
    fix_obsidian_config_drift()

    print(f"\n=== Optimization complete: {fixes} fixes applied ===")
    return fixes


if __name__ == "__main__":
    optimize()
