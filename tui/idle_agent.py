"""LACP Idle Agent — autoresearch-style self-improvement when idle.

When the user hasn't interacted for a configurable period, LACP spins up
a background agent that experiments on its own codebase:
- CSS/UX tweaks
- Prompt optimization
- Tool improvements
- Performance tuning

Follows Karpathy's autoresearch pattern: modify → test → keep/discard → repeat.

Usage:
    /autoresearch on       Start idle monitoring
    /autoresearch off      Stop
    /autoresearch status   Show experiment log
    /autoresearch config   Show/edit settings
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Callable


AUTORESEARCH_DIR = Path.home() / ".lacp" / "autoresearch"
LACP_ROOT = Path(__file__).parent.parent
RESULTS_FILE = AUTORESEARCH_DIR / "results.tsv"
LOG_FILE = AUTORESEARCH_DIR / "experiment.log"

# Default config
DEFAULT_CONFIG = {
    "idle_threshold_secs": 300,  # 5 min before starting
    "experiment_timeout_secs": 120,  # max 2 min per experiment
    "max_experiments": 50,  # safety limit per session
    "auto_start": False,  # require explicit /autoresearch on
    "agent": "codex",  # which agent to delegate to (codex = OpenAI gpt-5.3)
    "branch_prefix": "autoresearch",
}

def _load_program() -> str:
    """Load the autoresearch program from config file, or use inline default."""
    program_file = LACP_ROOT / "config" / "autoresearch-program.md"
    if program_file.exists():
        return program_file.read_text(encoding="utf-8").replace("{repo_root}", str(LACP_ROOT))
    # Inline fallback
    return f"""You are an autonomous researcher improving LACP at {LACP_ROOT}.
Only modify tui/ files. Run python3 {LACP_ROOT}/tui/autoresearch_metrics.py to measure health score.
Goal: maximize health score. Keep changes small (<30 lines). Commit improvements, revert failures.
NEVER STOP until manually interrupted."""


@dataclass
class Experiment:
    """Record of a single autoresearch experiment."""
    timestamp: str
    description: str
    status: str  # "keep", "discard", "crash"
    commit: str = ""
    duration_secs: float = 0.0


@dataclass
class IdleAgentState:
    """State of the idle agent."""
    enabled: bool = False
    running: bool = False
    last_input_time: float = 0.0
    experiments: list[Experiment] = field(default_factory=list)
    total_experiments: int = 0
    _thread: threading.Thread | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event)
    config: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_CONFIG))
    _on_status: Callable[[str], None] | None = None


class IdleAgent:
    """Manages the autoresearch idle loop."""

    def __init__(self, on_status: Callable[[str], None] | None = None) -> None:
        self.state = IdleAgentState()
        self.state._on_status = on_status
        AUTORESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def _log(self, msg: str) -> None:
        """Log to file and optional status callback."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        try:
            with open(LOG_FILE, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass
        if self.state._on_status:
            self.state._on_status(msg)

    def _load_history(self) -> None:
        """Load previous experiment results."""
        if RESULTS_FILE.exists():
            try:
                for line in RESULTS_FILE.read_text().splitlines()[1:]:  # skip header
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        self.state.experiments.append(Experiment(
                            timestamp=parts[0],
                            description=parts[3] if len(parts) > 3 else "",
                            status=parts[2],
                            commit=parts[1] if len(parts) > 1 else "",
                        ))
                self.state.total_experiments = len(self.state.experiments)
            except Exception:
                pass

    def _save_result(self, exp: Experiment) -> None:
        """Append experiment result to TSV."""
        if not RESULTS_FILE.exists():
            RESULTS_FILE.write_text("timestamp\tcommit\tstatus\tdescription\tduration\n")
        with open(RESULTS_FILE, "a") as f:
            f.write(f"{exp.timestamp}\t{exp.commit}\t{exp.status}\t{exp.description}\t{exp.duration_secs:.1f}\n")

    def touch_input(self) -> None:
        """Call this whenever the user sends input."""
        self.state.last_input_time = time.time()

    def start(self) -> None:
        """Enable idle monitoring."""
        if self.state.enabled:
            return
        self.state.enabled = True
        self.state._stop_event.clear()
        self.state._thread = threading.Thread(target=self._idle_loop, daemon=True)
        self.state._thread.start()
        self._log("Idle agent enabled — will start research after "
                  f"{self.state.config['idle_threshold_secs']}s idle")

    def start_now(self) -> None:
        """Start a research experiment immediately (no idle wait)."""
        self.state.enabled = True
        self.state._stop_event.clear()
        self._log("Starting autoresearch immediately...")
        thread = threading.Thread(target=self._run_experiment, daemon=True)
        thread.start()

    def stop(self) -> None:
        """Stop idle monitoring."""
        self.state.enabled = False
        self.state._stop_event.set()
        self.state.running = False
        self._log("Idle agent stopped")

    def _idle_loop(self) -> None:
        """Main loop — wait for idle, then run experiments."""
        while not self.state._stop_event.is_set():
            # Check if idle long enough
            idle_secs = time.time() - self.state.last_input_time
            threshold = self.state.config["idle_threshold_secs"]

            if idle_secs >= threshold and not self.state.running:
                self.state.running = True
                self._log(f"Idle for {idle_secs:.0f}s — starting autoresearch")
                self._run_experiment()
                self.state.running = False

            # Check every 30s
            self.state._stop_event.wait(30)

    def _get_baseline_score(self) -> float:
        """Run metrics to get current health score."""
        try:
            result = subprocess.run(
                ["python3", str(LACP_ROOT / "tui" / "autoresearch_metrics.py"), "--score"],
                capture_output=True, text=True, timeout=30,
                cwd=str(LACP_ROOT),
            )
            return float(result.stdout.strip()) if result.returncode == 0 else 0.0
        except Exception:
            return 0.0

    def _run_experiment(self) -> None:
        """Run a single autoresearch experiment via agent delegation."""
        if self.state.total_experiments >= self.state.config["max_experiments"]:
            self._log(f"Max experiments reached ({self.state.config['max_experiments']})")
            return

        start_time = time.time()
        agent = self.state.config["agent"]
        timeout = self.state.config["experiment_timeout_secs"]

        # Get baseline score before experiment
        baseline_score = self._get_baseline_score()
        self._log(f"Baseline health score: {baseline_score}")

        # Build the prompt
        program = _load_program()
        prompt = (
            f"Current LACP health score: {baseline_score}/100\n\n"
            f"Read this program and run ONE experiment:\n\n{program}\n\n"
            f"Pick a small improvement, make the change, validate with "
            f"python3 {LACP_ROOT}/tui/autoresearch_metrics.py --score, and report."
        )

        # Create branch if needed
        branch = f"{self.state.config['branch_prefix']}/{datetime.now(UTC).strftime('%Y%m%d')}"
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch],
                capture_output=True, text=True, timeout=10,
                cwd=str(LACP_ROOT),
            )
        except Exception:
            pass  # branch may already exist

        # Run the agent
        self._log(f"Running experiment via {agent}...")
        exp = Experiment(
            timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            description="",
            status="crash",
        )

        try:
            # Delegate to agent
            agent_cmds = {
                "claude": ["claude", "-p", prompt],
                "codex": ["codex", "exec", prompt],
                "hermes": ["hermes", "chat", "-Q", "-q", prompt],
            }
            cmd = agent_cmds.get(agent, agent_cmds["claude"])

            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout,
                cwd=str(LACP_ROOT),
                env={**os.environ, "LACP_BYPASS": "1"},
            )

            output = result.stdout.strip()
            exp.duration_secs = time.time() - start_time

            # Validate — check health score improved or maintained
            new_score = self._get_baseline_score()
            exp.duration_secs = time.time() - start_time

            if new_score >= baseline_score:
                # Get latest commit
                commit_result = subprocess.run(
                    ["git", "log", "--oneline", "-1"],
                    capture_output=True, text=True, timeout=5,
                    cwd=str(LACP_ROOT),
                )
                exp.commit = commit_result.stdout.strip()[:7]
                exp.status = "keep"
                delta = new_score - baseline_score
                desc = output[:150] if output else "experiment completed"
                exp.description = f"[{baseline_score}→{new_score} Δ{delta:+.1f}] {desc}"
                self._log(f"KEEP ({baseline_score}→{new_score}): {desc[:60]}")
            else:
                # Revert — score decreased
                subprocess.run(
                    ["git", "checkout", "--", "tui/"],
                    capture_output=True, timeout=10,
                    cwd=str(LACP_ROOT),
                )
                delta = new_score - baseline_score
                exp.status = "discard"
                exp.description = f"[{baseline_score}→{new_score} Δ{delta:+.1f}] score decreased"
                self._log(f"DISCARD ({baseline_score}→{new_score}): score decreased")

        except subprocess.TimeoutExpired:
            exp.status = "crash"
            exp.description = f"timed out after {timeout}s"
            exp.duration_secs = time.time() - start_time
            self._log(f"Experiment CRASH: timeout")
        except Exception as e:
            exp.status = "crash"
            exp.description = str(e)[:200]
            exp.duration_secs = time.time() - start_time
            self._log(f"Experiment CRASH: {e}")

        # Save result
        self.state.experiments.append(exp)
        self.state.total_experiments += 1
        self._save_result(exp)

        # Switch back to main
        try:
            subprocess.run(
                ["git", "checkout", "main"],
                capture_output=True, timeout=10,
                cwd=str(LACP_ROOT),
            )
        except Exception:
            pass

    def status(self) -> str:
        """Get human-readable status."""
        lines = [
            f"Idle Agent: {'[green]enabled[/]' if self.state.enabled else '[dim]disabled[/]'}",
            f"Running: {'[green]yes[/]' if self.state.running else '[dim]no[/]'}",
            f"Experiments: {self.state.total_experiments}",
        ]

        idle_secs = time.time() - self.state.last_input_time if self.state.last_input_time else 0
        threshold = self.state.config["idle_threshold_secs"]
        if self.state.enabled:
            if idle_secs >= threshold:
                lines.append(f"Idle: {idle_secs:.0f}s (threshold: {threshold}s) — [green]research active[/]")
            else:
                remaining = threshold - idle_secs
                lines.append(f"Idle: {idle_secs:.0f}s (starts in {remaining:.0f}s)")

        if self.state.experiments:
            lines.append("\nRecent experiments:")
            for exp in self.state.experiments[-5:]:
                status_icon = {"keep": "✅", "discard": "❌", "crash": "💥"}.get(exp.status, "?")
                lines.append(f"  {status_icon} {exp.description[:60]}  ({exp.duration_secs:.0f}s)")

        return "\n".join(lines)

    @property
    def experiment_count(self) -> int:
        return self.state.total_experiments

    @property
    def is_researching(self) -> bool:
        return self.state.running
