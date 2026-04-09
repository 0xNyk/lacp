#!/usr/bin/env python3
"""UserPromptSubmit hook — nudges user to state their thinking before asking questions.

Opt-in via LACP_THINKING_NUDGE=1 or the thinking-partner context mode.

Hook protocol (UserPromptSubmit):
  - exit 0 with {"systemMessage": "..."} → inject reminder
  - exit 0 with no output → no-op
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Only active when explicitly enabled
ENABLED = (
    os.getenv("LACP_THINKING_NUDGE", "0") == "1"
    or os.getenv("LACP_CONTEXT_MODE", "").strip() == "thinking-partner"
)

# Minimum prompt length to analyze (skip trivial/command prompts)
MIN_LENGTH = 30

# Patterns that indicate the user is asking for answers without stating their position
BARE_QUESTION_PATTERNS = [
    re.compile(r"^(?:what|how|why|should|can|could|would)\s+(?:should|do|would|is|are|can)\b", re.IGNORECASE),
    re.compile(r"^(?:tell me|explain|help me|give me)\b", re.IGNORECASE),
    re.compile(r"^(?:what(?:'s| is) the best)\b", re.IGNORECASE),
    re.compile(r"^(?:which|what) (?:approach|strategy|option|way)\b", re.IGNORECASE),
]

# Patterns that indicate the user IS stating their thinking (no nudge needed)
POSITION_INDICATORS = [
    re.compile(r"\bI think\b", re.IGNORECASE),
    re.compile(r"\bI believe\b", re.IGNORECASE),
    re.compile(r"\bmy (?:thinking|position|view|take|approach|plan|hypothesis)\b", re.IGNORECASE),
    re.compile(r"\bhere(?:'s| is) (?:my|what I)\b", re.IGNORECASE),
    re.compile(r"\bI(?:'m| am) (?:leaning|considering|thinking)\b", re.IGNORECASE),
    re.compile(r"\bbecause I\b", re.IGNORECASE),
    re.compile(r"\bmy reasoning\b", re.IGNORECASE),
    re.compile(r"\bI(?:'ve| have) (?:been|already)\b", re.IGNORECASE),
]

# Skip nudge for implementation-type prompts (the user wants action, not dialogue)
IMPLEMENTATION_PATTERNS = [
    re.compile(r"^(?:fix|implement|add|create|write|build|update|refactor|delete|remove|rename|move|run|test|deploy)\b", re.IGNORECASE),
    re.compile(r"^(?:please |can you )?(?:fix|implement|add|create|write|build|update|refactor)\b", re.IGNORECASE),
    re.compile(r"^/", re.IGNORECASE),  # slash commands
]

NUDGE_MESSAGE = (
    "Thinking partner reminder: Before I answer, consider stating your current "
    "thinking first — even if half-formed. This sharpens your reasoning and helps "
    "me challenge your assumptions rather than just provide answers. "
    "What is your current position on this?"
)

# Session-level cooldown: don't nudge more than once per N prompts
COOLDOWN_PROMPTS = 5
_STATE_DIR = Path.home() / ".lacp" / "hooks" / "state"


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def _should_nudge(prompt: str) -> bool:
    """Returns True if the prompt looks like a bare question without stated position."""
    stripped = prompt.strip()

    # Too short to analyze
    if len(stripped) < MIN_LENGTH:
        return False

    # User is giving an implementation command — don't interrupt
    for rx in IMPLEMENTATION_PATTERNS:
        if rx.search(stripped):
            return False

    # User already stated their position
    for rx in POSITION_INDICATORS:
        if rx.search(stripped):
            return False

    # Check if it's a bare question
    for rx in BARE_QUESTION_PATTERNS:
        if rx.search(stripped):
            return True

    return False


def _check_cooldown(session_id: str) -> bool:
    """Returns True if we should suppress the nudge (cooldown active)."""
    if not session_id:
        return False
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    counter_file = _STATE_DIR / safe_id / "nudge-count"
    try:
        if counter_file.exists():
            count = int(counter_file.read_text().strip())
            if count > 0:
                # Decrement counter
                counter_file.write_text(str(count - 1))
                return True
        return False
    except (ValueError, OSError):
        return False


def _set_cooldown(session_id: str) -> None:
    """Set cooldown counter after a nudge."""
    if not session_id:
        return
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    counter_dir = _STATE_DIR / safe_id
    try:
        counter_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (counter_dir / "nudge-count").write_text(str(COOLDOWN_PROMPTS))
    except OSError:
        pass


def main() -> None:
    if not ENABLED:
        return

    payload = _read_payload()
    prompt = payload.get("prompt") or payload.get("user_prompt") or ""
    session_id = payload.get("session_id") or ""

    if not prompt.strip():
        return

    if _check_cooldown(session_id):
        return

    if _should_nudge(prompt):
        _set_cooldown(session_id)
        print(json.dumps({"systemMessage": NUDGE_MESSAGE}))


if __name__ == "__main__":
    main()
