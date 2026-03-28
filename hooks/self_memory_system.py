#!/usr/bin/env python3
"""Self-Memory System (SMS) — Psychology-informed agent memory.

Implements Conway's Self-Memory System (2005) with five principles:
1. Hierarchical temporal organization (life periods → events → details)
2. Goal-relevant filtering (working self gates retrieval)
3. Emotional weighting (significance scoring biases recall)
4. Narrative coherence (story across sessions)
5. Co-emergent self-model (identity ↔ memory feedback loop)

References:
- Conway, M.A. (2005). Memory and the self. Journal of Memory and Language.
- Damasio, A. (1994). Descartes' Error: Emotion, Reason, and the Human Brain.
- Rathbone, C.J. et al. (2008). Self-defining memories across the lifespan.
- Klein, S.B. & Nichols, S. (2012). Memory and the sense of personal identity.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# -- Configuration --

SMS_ROOT = Path(os.getenv("LACP_SMS_ROOT", str(Path.home() / ".lacp" / "sms")))
FOCUS_FILE = Path(os.getenv("LACP_FOCUS_FILE", str(Path.home() / ".lacp" / "focus.md")))


# -- Principle 1: Hierarchical Temporal Organization --

@dataclass
class Episode:
    """A single meaningful interaction unit (session or significant event)."""
    session_id: str
    project: str
    started_at: str
    ended_at: str = ""
    summary: str = ""
    files_touched: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    significance: float = 0.5  # 0-1, Principle 3
    epoch_id: str = ""  # which epoch this belongs to


@dataclass
class Epoch:
    """A life period / project phase grouping episodes by theme."""
    epoch_id: str
    label: str  # e.g., "LACP harness overhaul", "Q1 2026 knowledge work"
    started_at: str
    ended_at: str = ""
    theme: str = ""  # recurring pattern or focus
    episode_count: int = 0
    key_decisions: list[str] = field(default_factory=list)
    identity_shifts: list[str] = field(default_factory=list)  # "became X", "stopped doing Y"


def _epochs_file() -> Path:
    return SMS_ROOT / "epochs.jsonl"


def _episodes_file() -> Path:
    return SMS_ROOT / "episodes.jsonl"


def write_episode(episode: Episode) -> None:
    """Append an episode to the episodes log."""
    SMS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(_episodes_file(), "a") as f:
        f.write(json.dumps(asdict(episode), default=str) + "\n")


def write_epoch(epoch: Epoch) -> None:
    """Append or update an epoch."""
    SMS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(_epochs_file(), "a") as f:
        f.write(json.dumps(asdict(epoch), default=str) + "\n")


def _decay_significance(raw_significance: float, age_days: float) -> float:
    """Apply time-based decay to significance (FSRS-inspired).

    Rathbone: memories cluster around identity transitions (high significance).
    Routine memories decay faster. Highly significant memories decay slowly.
    """
    if raw_significance >= 0.8:
        # Identity-defining moments decay very slowly (half-life ~90 days)
        decay_rate = 0.0077
    elif raw_significance >= 0.6:
        # Important events decay moderately (half-life ~30 days)
        decay_rate = 0.023
    else:
        # Routine events decay quickly (half-life ~7 days)
        decay_rate = 0.099

    decayed = raw_significance * (0.5 ** (age_days * decay_rate))
    return max(0.01, decayed)  # never fully zero


def read_episodes(days: int = 30, min_significance: float = 0.0,
                  apply_decay: bool = True) -> list[dict]:
    """Read episodes within time window, filtered by significance.

    When apply_decay=True, significance scores are adjusted for age
    (Rathbone: identity-defining moments persist, routine fades).
    """
    cutoff = time.time() - (days * 86400)
    now = time.time()
    episodes = []
    ep_file = _episodes_file()
    if not ep_file.is_file():
        return []
    for line in ep_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            ep = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Parse timestamp
        ts_str = ep.get("started_at", "")
        try:
            ts = time.mktime(time.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S"))
            if ts < cutoff:
                continue
        except (ValueError, TypeError):
            continue

        if apply_decay:
            age_days = (now - ts) / 86400
            raw_sig = ep.get("significance", 0.3)
            ep["significance"] = round(_decay_significance(raw_sig, age_days), 3)
            ep["raw_significance"] = raw_sig

        if ep.get("significance", 0) >= min_significance:
            episodes.append(ep)
    return episodes


def read_epochs() -> list[dict]:
    """Read all epochs."""
    ep_file = _epochs_file()
    if not ep_file.is_file():
        return []
    epochs = []
    for line in ep_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            epochs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return epochs


def synthesize_epoch(label: str, days: int = 30) -> Epoch:
    """Create an epoch from recent episodes (weekly/monthly synthesis)."""
    episodes = read_episodes(days=days, min_significance=0.3)
    decisions = []
    for ep in episodes:
        decisions.extend(ep.get("decisions_made", []))

    epoch = Epoch(
        epoch_id=f"epoch-{int(time.time())}",
        label=label,
        started_at=episodes[0]["started_at"] if episodes else time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        theme="",
        episode_count=len(episodes),
        key_decisions=decisions[:10],  # top 10
        identity_shifts=[],
    )
    return epoch


# -- Principle 2: Goal-Relevant Filtering (Working Self) --

def read_working_self() -> dict:
    """Read current goals from focus brief — the 'working self' that gates retrieval."""
    if not FOCUS_FILE.is_file():
        return {"current_problem": "", "beliefs": "", "decisions": "", "output_goal": ""}

    content = FOCUS_FILE.read_text()
    sections = {}
    current_section = ""
    current_content = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = line[3:].strip().lower()
            current_content = []
        else:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return {
        "current_problem": sections.get("1. current problem", ""),
        "beliefs": sections.get("2. beliefs and uncertainties", ""),
        "decisions": sections.get("3. open decisions", ""),
        "output_goal": sections.get("4. 30-day output", ""),
    }


def goal_relevance_score(memory_text: str, working_self: dict) -> float:
    """Score how relevant a memory is to current goals (0-1).

    Simple keyword overlap — could be upgraded to embeddings later.
    """
    if not working_self.get("current_problem"):
        return 0.5  # No goal context → neutral

    goal_words = set()
    for v in working_self.values():
        if isinstance(v, str):
            goal_words.update(w.lower() for w in v.split() if len(w) > 3)

    if not goal_words:
        return 0.5

    memory_words = set(w.lower() for w in memory_text.split() if len(w) > 3)
    overlap = len(goal_words & memory_words)
    return min(1.0, overlap / max(len(goal_words) * 0.3, 1))


def goal_filtered_query(query: str) -> str:
    """Prepend goal context to a search query for goal-relevant retrieval.

    Conway's working self: retrieval is gated by current goals.
    Instead of modifying the MCP server, we modify the query itself
    to bias results toward goal-relevant content.
    """
    ws = read_working_self()
    problem = ws.get("current_problem", "").strip()
    # Strip template placeholders
    if "<!-- Replace" in problem or not problem or len(problem) < 10:
        return query  # No goal context available

    # Extract key terms from current problem (first sentence)
    first_sentence = problem.split("\n")[0].strip()[:100]
    return f"{query} (context: {first_sentence})"


# -- Principle 3: Emotional/Significance Weighting --

# Significance markers — patterns that indicate high-significance events
SIGNIFICANCE_MARKERS = {
    "breakthrough": 0.9,
    "critical": 0.8,
    "failure": 0.8,
    "regret": 0.8,
    "turning point": 0.9,
    "lesson learned": 0.7,
    "decision": 0.6,
    "mistake": 0.7,
    "insight": 0.7,
    "blocked": 0.6,
    "resolved": 0.5,
    "shipped": 0.6,
    "broke": 0.8,
    "fixed": 0.5,
    "discovered": 0.7,
    "surprised": 0.7,
}


def compute_significance(text: str, had_test_failures: bool = False,
                         files_changed: int = 0, was_blocked: bool = False) -> float:
    """Compute significance score (0-1) based on content and context signals."""
    score = 0.3  # baseline

    # Marker-based scoring
    lower = text.lower()
    for marker, weight in SIGNIFICANCE_MARKERS.items():
        if marker in lower:
            score = max(score, weight)

    # Context signals (Damasio: somatic markers from environment)
    if had_test_failures:
        score = max(score, 0.7)  # Test failures = learning moment
    if was_blocked:
        score = max(score, 0.6)  # Being blocked = frustration marker
    if files_changed > 10:
        score = max(score, 0.6)  # Large change = significant event

    return min(1.0, score)


# -- Principle 4: Narrative Coherence --

@dataclass
class AgentNarrative:
    """The agent's evolving story — who am I, how am I changing."""
    agent_id: str
    current_arc: str = ""  # e.g., "building a control plane for agent sessions"
    recurring_themes: list[str] = field(default_factory=list)
    strengths_demonstrated: list[str] = field(default_factory=list)
    growth_edges: list[str] = field(default_factory=list)  # areas of struggle/growth
    decisions_and_outcomes: list[dict] = field(default_factory=list)  # [{decision, outcome, learned}]
    last_synthesized: str = ""


def _narrative_file() -> Path:
    return SMS_ROOT / "narrative.json"


def read_narrative() -> Optional[AgentNarrative]:
    """Read the current agent narrative."""
    nf = _narrative_file()
    if not nf.is_file():
        return None
    try:
        data = json.loads(nf.read_text())
        return AgentNarrative(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def write_narrative(narrative: AgentNarrative) -> None:
    """Write the agent narrative."""
    SMS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    _narrative_file().write_text(json.dumps(asdict(narrative), indent=2))


# -- Principle 5: Co-Emergent Self-Model --

@dataclass
class SelfModel:
    """The agent's evolving self-model — bootstrapped from memory, gates memory."""
    agent_id: str
    # Inferred from session patterns
    preferred_approaches: list[str] = field(default_factory=list)  # e.g., "test-first", "incremental"
    known_biases: list[str] = field(default_factory=list)  # e.g., "over-engineers", "skips tests"
    effective_contexts: list[str] = field(default_factory=list)  # e.g., "works best with clear specs"
    # Updated from outcomes
    success_patterns: list[str] = field(default_factory=list)  # what worked
    failure_patterns: list[str] = field(default_factory=list)  # what didn't
    # Meta
    confidence_in_self_model: float = 0.3  # how much data backs this model
    last_updated: str = ""
    update_count: int = 0


def _self_model_file() -> Path:
    return SMS_ROOT / "self-model.json"


def read_self_model() -> Optional[SelfModel]:
    """Read the current self-model."""
    sf = _self_model_file()
    if not sf.is_file():
        return None
    try:
        data = json.loads(sf.read_text())
        return SelfModel(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def write_self_model(model: SelfModel) -> None:
    """Write the self-model."""
    SMS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    model.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    model.update_count += 1
    # Confidence grows with more updates (asymptotic to 0.9)
    model.confidence_in_self_model = min(0.9, 0.3 + (model.update_count * 0.05))
    _self_model_file().write_text(json.dumps(asdict(model), indent=2))


# -- Integration: Session Context Builder --

def build_session_context(agent_id: str = "", project: str = "") -> str:
    """Build psychology-informed context for session start injection.

    Combines all 5 principles into a coherent context block.
    """
    parts = []

    # Principle 2: Working self (current goals)
    ws = read_working_self()
    if ws.get("current_problem"):
        parts.append(f"Current focus: {ws['current_problem'][:200]}")

    # Principle 5: Self-model
    sm = read_self_model()
    if sm and sm.confidence_in_self_model > 0.4:
        if sm.preferred_approaches:
            parts.append(f"Preferred approaches: {', '.join(sm.preferred_approaches[:3])}")
        if sm.known_biases:
            parts.append(f"Watch for: {', '.join(sm.known_biases[:3])}")
        if sm.failure_patterns:
            parts.append(f"Past failures: {', '.join(sm.failure_patterns[:2])}")

    # Principle 4: Narrative arc
    narrative = read_narrative()
    if narrative and narrative.current_arc:
        parts.append(f"Current arc: {narrative.current_arc[:200]}")

    # Principle 1: Recent significant episodes (hierarchical — only high-significance)
    episodes = read_episodes(days=7, min_significance=0.6)
    if episodes:
        recent = episodes[-3:]  # last 3 significant episodes
        ep_summaries = []
        for ep in recent:
            summary = ep.get("summary", "")[:80]
            sig = ep.get("significance", 0)
            if summary:
                ep_summaries.append(f"  [{sig:.1f}] {summary}")
        if ep_summaries:
            parts.append("Recent significant episodes:\n" + "\n".join(ep_summaries))

    # Principle 3: Significance-weighted retrieval note
    if episodes:
        avg_sig = sum(ep.get("significance", 0) for ep in episodes) / len(episodes)
        if avg_sig > 0.7:
            parts.append("Note: Recent work has been high-significance. Extra care warranted.")

    return "\n".join(parts) if parts else ""


# -- Principle 5: Self-Model Auto-Update --

def update_self_model_from_session(
    session_summary: str,
    files_changed: int,
    had_test_failures: bool,
    was_blocked: bool,
    significance: float,
) -> None:
    """Update self-model from session outcomes (co-emergent identity loop).

    Klein & Nichols: identity and memory bootstrap each other.
    After each session, infer patterns and update the self-model.
    """
    sm = read_self_model()
    if sm is None:
        sm = SelfModel(agent_id="auto")

    lower = session_summary.lower() if session_summary else ""

    # Infer success/failure patterns from session signals
    if had_test_failures and significance > 0.5:
        pattern = "test failures during high-significance work"
        if pattern not in sm.failure_patterns:
            sm.failure_patterns.append(pattern)
            # Keep list bounded
            sm.failure_patterns = sm.failure_patterns[-10:]

    if was_blocked and significance > 0.5:
        pattern = "blocked during important work"
        if pattern not in sm.failure_patterns:
            sm.failure_patterns.append(pattern)
            sm.failure_patterns = sm.failure_patterns[-10:]

    if files_changed > 15 and not had_test_failures:
        pattern = "large successful changes (15+ files, tests pass)"
        if pattern not in sm.success_patterns:
            sm.success_patterns.append(pattern)
            sm.success_patterns = sm.success_patterns[-10:]

    if files_changed > 0 and not had_test_failures and significance >= 0.6:
        pattern = "productive high-significance session"
        if pattern not in sm.success_patterns:
            sm.success_patterns.append(pattern)
            sm.success_patterns = sm.success_patterns[-10:]

    # Infer approach preferences from content
    if "test" in lower and "first" in lower:
        pref = "test-first"
        if pref not in sm.preferred_approaches:
            sm.preferred_approaches.append(pref)
    if "incremental" in lower or "step by step" in lower:
        pref = "incremental implementation"
        if pref not in sm.preferred_approaches:
            sm.preferred_approaches.append(pref)

    write_self_model(sm)


# -- CLI entry point for testing --

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "context"

    if cmd == "context":
        ctx = build_session_context()
        print(ctx if ctx else "(no SMS context available)")
    elif cmd == "working-self":
        print(json.dumps(read_working_self(), indent=2))
    elif cmd == "episodes":
        eps = read_episodes(days=int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        print(json.dumps(eps, indent=2))
    elif cmd == "epochs":
        print(json.dumps(read_epochs(), indent=2))
    elif cmd == "narrative":
        n = read_narrative()
        print(json.dumps(asdict(n), indent=2) if n else '{"status": "no narrative"}')
    elif cmd == "self-model":
        sm = read_self_model()
        print(json.dumps(asdict(sm), indent=2) if sm else '{"status": "no self-model"}')
    else:
        print(f"Usage: python3 self_memory_system.py [context|working-self|episodes|epochs|narrative|self-model]")
