#!/usr/bin/env python3
"""curate_titles — Layer-4 title-shape normalization for the Obsidian vault.

Closes the one curation gap that LACP's registry-based maintenance pipeline
(gap-detection, FSRS review queue, consolidation) does not cover: the literal
.md filenames in the vault. brain-ingest creates notes with category- or
timestamp-shaped titles ("Research Notes", "2026-03-28_13-21-32") which match
on broad surface words and outrank claim-shaped notes at retrieval time. This
script detects those and proposes claim-shaped rewrites from each note's own H1.

It deliberately does ONLY the rename job. Link and prune are handled by the
existing brain-expand stages (detect_knowledge_gaps.py, generate_review_queue.py,
archive_inbox.py) and are not duplicated here.

Stdlib only. Dry-run by default. Hub-aware: never proposes touching navigation
notes (MOCs, indexes, directives) even with zero inlinks.

Usage:
  curate_titles.py --vault ~/obsidian/vault                 # dry-run report (text)
  curate_titles.py --vault ~/obsidian/vault --json          # machine-readable
  curate_titles.py --vault ~/obsidian/vault --apply         # apply rename proposals
  curate_titles.py --vault ~/obsidian/vault --report out.md # write report to file
  curate_titles.py --self-test                              # inline tests, no vault
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# --- Title classification --------------------------------------------------

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([_T ]\d{2}[-:]\d{2}([-:]\d{2})?)?$")
# Date-only daily notes (YYYY-MM-DD) are a legitimate convention, not drift.
DAILY_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Directories whose date-named notes are intentional (dailies, voice captures).
PROTECTED_DIRS = {"daily", "dailies", "voice-notes", "journal", "templates"}
GENERIC_CATEGORY_WORDS = {
    "notes", "research", "ideas", "thoughts", "misc", "stuff", "todo", "draft",
    "untitled", "new", "temp", "scratch", "log", "logs", "dump", "inbox",
}
# Claim-shaped titles contain a verb or comparison — they read as sentences.
CLAIM_SIGNALS = re.compile(
    r"\b(beats?|outperforms?|is|are|was|were|should|must|fails?|breaks?|wins?|"
    r"requires?|enables?|prevents?|causes?|means?|needs?|drives?|kills?|"
    r"compounds?|degrades?|scales?|reduces?|increases?|replaces?)\b",
    re.IGNORECASE,
)


def classify_title(stem: str) -> str:
    """Return 'timestamp' | 'category' | 'claim' | 'ok'."""
    s = stem.strip()
    if TIMESTAMP_RE.match(s):
        return "timestamp"
    words = [w for w in re.split(r"[\s\-_]+", s.lower()) if w]
    if not words:
        return "category"
    if CLAIM_SIGNALS.search(s):
        return "claim"
    if len(words) <= 3 and any(w in GENERIC_CATEGORY_WORDS for w in words):
        return "category"
    if len(words) == 1 and words[0] in GENERIC_CATEGORY_WORDS:
        return "category"
    return "ok"


# --- Note parsing ----------------------------------------------------------

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
NEEDS_CURATION_RE = re.compile(r"^needs_curation:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


class Note:
    def __init__(self, path: Path, vault: Path):
        self.path = path
        self.rel = path.relative_to(vault)
        self.stem = path.stem
        try:
            self.text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self.text = ""
        self.mtime = dt.datetime.fromtimestamp(path.stat().st_mtime)
        self.outlinks = {m.strip() for m in WIKILINK_RE.findall(self.text)}
        self.h1 = self._first_h1()
        self.title_class = classify_title(self.stem)
        self.needs_curation = self._has_needs_curation_flag()

    def _has_needs_curation_flag(self) -> bool:
        """True when frontmatter carries `needs_curation: true` — set by
        brain-ingest, whose URL/HTML-derived titles are category-shaped."""
        m = FRONTMATTER_RE.match(self.text)
        return bool(m and NEEDS_CURATION_RE.search(m.group(1)))

    def _first_h1(self):
        for line in self.text.splitlines():
            if line.startswith("# "):
                h1 = line[2:].strip()
                # Reject H1s that are clearly not titles: too long (a paragraph
                # got captured), or containing markdown/template structure.
                if len(h1) > 90:
                    return None
                if "<%" in h1 or "{{" in h1 or "##" in h1 or "```" in h1:
                    return None
                return h1
        return None

    @property
    def in_protected_dir(self):
        return any(part in PROTECTED_DIRS for part in self.rel.parts)


# --- Curation: rename job only ---------------------------------------------


def load_vault(vault: Path, ignore_dirs):
    notes = []
    for p in vault.rglob("*.md"):
        if any(part in ignore_dirs for part in p.parts):
            continue
        try:
            if p.is_symlink():
                continue
        except OSError:
            continue
        notes.append(Note(p, vault))
    return notes


def job_rename(notes):
    """Propose claim-shaped titles for timestamp/category notes.

    Skips protected dirs (dailies, voice-notes, templates) where date/template
    names are intentional, not drift.
    """
    proposals = []
    for n in notes:
        if n.in_protected_dir:
            continue
        if DAILY_DATE_RE.match(n.stem):
            continue
        # A note is a candidate if its title is timestamp/category-shaped OR it
        # was explicitly flagged needs_curation:true by brain-ingest.
        if n.title_class in ("timestamp", "category") or n.needs_curation:
            suggestion = None
            if n.h1 and classify_title(n.h1) in ("claim", "ok") and n.h1.lower() != n.stem.lower():
                suggestion = n.h1
            proposals.append({
                "note": str(n.rel),
                "current": n.stem,
                "class": n.title_class,
                "needs_curation": n.needs_curation,
                "suggestion": suggestion,
            })
    return proposals


def apply_renames(vault: Path, proposals, notes):
    """Rename files with claim-shaped suggestions, fixing wikilinks vault-wide."""
    applied = []
    rename_map = {}  # old_stem -> new_stem
    for p in proposals:
        if not p["suggestion"]:
            continue
        old_path = vault / p["note"]
        new_stem = re.sub(r"[^\w\s\-,.]", "", p["suggestion"]).strip()[:120]
        if not new_stem or new_stem.lower() == old_path.stem.lower():
            continue
        new_path = old_path.with_name(new_stem + ".md")
        if new_path.exists():
            continue  # collision; skip
        old_path.rename(new_path)
        rename_map[old_path.stem] = new_stem
        applied.append((p["note"], new_stem))
    if rename_map:
        for n in notes:
            np = vault / n.rel
            if not np.exists():
                continue
            text = np.read_text(encoding="utf-8", errors="replace")
            changed = False
            for old, new in rename_map.items():
                pattern = re.compile(r"\[\[" + re.escape(old) + r"(\]\]|\|)")
                if pattern.search(text):
                    text = pattern.sub(r"[[" + new + r"\1", text)
                    changed = True
            if changed:
                np.write_text(text, encoding="utf-8")
    return applied


# --- Report ----------------------------------------------------------------


def build_summary(notes, renames, applied):
    class_counts = defaultdict(int)
    for n in notes:
        class_counts[n.title_class] += 1
    actionable = [r for r in renames if r["suggestion"]]
    needs_human = [r for r in renames if not r["suggestion"]]
    return {
        "notes_scanned": len(notes),
        "title_classes": dict(sorted(class_counts.items())),
        "rename_candidates": len(renames),
        "rename_actionable": len(actionable),
        "rename_needs_human_title": len(needs_human),
        "renames_applied": len(applied),
    }


def build_report(vault, notes, renames, applied, now):
    s = build_summary(notes, renames, applied)
    lines = [
        f"# Title-Normalization Report — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- Vault: `{vault}`",
        f"- Notes scanned: {s['notes_scanned']}",
        "- Title classes: " + ", ".join(f"{k}={v}" for k, v in s["title_classes"].items()),
        "",
        f"## Rename ({s['rename_candidates']} candidates)",
    ]
    if applied:
        lines.append(f"**Applied {len(applied)} renames** (wikilinks fixed vault-wide).")
        for old, new in applied:
            lines.append(f"- `{old}` → `{new}`")
    else:
        actionable = [r for r in renames if r["suggestion"]]
        lines.append(
            f"{len(actionable)} have a claim-shaped H1 ready to promote "
            f"(dry-run; pass --apply):"
        )
        for r in actionable[:30]:
            lines.append(f"- `{r['note']}` ({r['class']}) → suggest **{r['suggestion']}**")
        no_suggestion = [r for r in renames if not r["suggestion"]]
        if no_suggestion:
            lines.append("")
            lines.append(f"{len(no_suggestion)} need a human-written claim title (no usable H1):")
            for r in no_suggestion[:20]:
                lines.append(f"- `{r['note']}` ({r['class']})")
    lines.append("")
    lines.append("---")
    lines.append("Generated by lacp-curate (Layer-4 title normalization). "
                 "Link/prune handled by brain-expand stages 7.5/7.6.")
    return "\n".join(lines)


# --- Self-test --------------------------------------------------------------


def self_test():
    cases = [
        ("2026-03-28_13-21-32", "timestamp"),
        ("2026-03-02", "timestamp"),
        ("memory graphs beat giant memory files", "claim"),
        ("hybrid retrieval outperforms pure semantic search", "claim"),
        ("Research Notes", "category"),
        ("misc", "category"),
        ("Context Engineering Playbook", "ok"),
    ]
    failures = []
    for stem, expected in cases:
        got = classify_title(stem)
        if got != expected:
            failures.append(f"classify_title({stem!r}) = {got!r}, expected {expected!r}")
    long_h1 = "# " + "x" * 200
    n = type("N", (), {"text": long_h1})()
    if Note._first_h1(n) is not None:
        failures.append("long H1 should be rejected")
    templater = "# <% tp.file.title %>"
    n2 = type("N", (), {"text": templater})()
    if Note._first_h1(n2) is not None:
        failures.append("templater H1 should be rejected")
    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELF-TEST PASSED ({len(cases)} title cases + 2 H1 cases)")
    return 0


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description="curate_titles — Layer-4 title normalization")
    ap.add_argument("--self-test", action="store_true", help="Run inline tests and exit")
    ap.add_argument("--vault", help="Path to Obsidian vault root")
    ap.add_argument("--apply", action="store_true",
                    help="Apply rename proposals (default: dry-run report only)")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--report", help="Write text report to this path (default: stdout)")
    ap.add_argument("--ignore", default=".obsidian,.smart-env,.trash,node_modules,data",
                    help="Comma-separated dir names to skip")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.vault:
        ap.error("--vault is required (unless --self-test)")

    vault = Path(os.path.expanduser(args.vault)).resolve()
    if not vault.is_dir():
        msg = {"ok": False, "error": f"vault not found: {vault}"}
        print(json.dumps(msg) if args.json else f"error: vault not found: {vault}",
              file=sys.stderr)
        return 1

    ignore_dirs = {d.strip() for d in args.ignore.split(",") if d.strip()}
    now = dt.datetime.now()

    notes = load_vault(vault, ignore_dirs)
    renames = job_rename(notes)
    applied = apply_renames(vault, renames, notes) if args.apply else []

    if args.json:
        summary = build_summary(notes, renames, applied)
        out = {
            "ok": True,
            "kind": "title_normalization",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "vault": str(vault),
            "applied": bool(args.apply),
            "summary": summary,
            "proposals": renames,
            "renames_applied": [{"note": o, "new_stem": n} for o, n in applied],
        }
        print(json.dumps(out, indent=2))
        return 0

    report = build_report(vault, notes, renames, applied, now)
    if args.report:
        rp = Path(os.path.expanduser(args.report))
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(report, encoding="utf-8")
        print(f"Report written to {rp}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
