#!/usr/bin/env python3
"""Stop Quality Gate — modular Python replacement for stop_quality_gate.sh.

Evaluates whether Claude is rationalizing incomplete work.
Uses fast heuristic pre-checks, optional test verification, and Ollama LLM eval.

Hook protocol (command-type Stop hook):
  - exit 0 with no stdout → allow stop
  - exit 0 with {"decision": "block", "reason": "..."} → block stop
  - exit 0 with {"decision": "allow", "systemMessage": "..."} → allow + inject feedback
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# -- Configuration (env var overrides) --

OLLAMA_URL = os.getenv("LACP_QUALITY_GATE_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("LACP_QUALITY_GATE_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = int(os.getenv("LACP_QUALITY_GATE_TIMEOUT", "25"))
DEBUG = os.getenv("LACP_QUALITY_GATE_DEBUG", "0") == "1"
MAX_BLOCKS = int(os.getenv("LACP_QUALITY_GATE_MAX_BLOCKS", "3"))

BLIND_SPOT_ENABLED = os.getenv("LACP_BLIND_SPOT_ENABLED", "0") == "1"

QUALITY_GATE_THRESHOLD = float(os.getenv("LACP_QUALITY_GATE_THRESHOLD", "2.5"))

OLLAMA_BASE = OLLAMA_URL.rsplit("/api/chat", 1)[0] if "/api/chat" in OLLAMA_URL else OLLAMA_URL
_LACP_STATE_DIR = Path.home() / ".lacp" / "hooks" / "state"
DEBUG_LOG = _LACP_STATE_DIR / "quality-gate.log"
RALPH_STATE_FILE = ".claude/ralph-loop.local.md"

# Allowed test runner prefixes — commands must start with one of these
_ALLOWED_TEST_RUNNERS = (
    "bun test", "pnpm test", "yarn test", "npm test",
    "make test", "cargo test", "python3 -m pytest",
    "bin/lacp-test",
)

HOOKS_DIR = Path(__file__).parent

# -- Imports from sibling modules --

sys.path.insert(0, str(HOOKS_DIR))
from detect_session_changes import scan_transcript  # noqa: E402
from hook_telemetry import log_decision  # noqa: E402


# -- Data types --

@dataclass
class CheckResult:
    decision: str  # "allow" or "block"
    reason: str = ""
    system_message: str = ""


@dataclass
class Context:
    hook_input: dict
    session_id: str
    cwd: str
    last_message: str
    stripped: str
    transcript_path: str
    stop_hook_active: bool
    ralph_active: bool


@dataclass
class ScoringResult:
    completeness: float = 0.0   # 1-5: Did they finish what they committed to?
    honesty: float = 0.0        # 1-5: Are claims about tests/status verified?
    deferral_ratio: float = 0.0 # 1-5: How little was pushed to "later"? (5=nothing deferred)
    work_evidence: float = 0.0  # 1-5: Files changed relative to scope claimed
    reasoning: str = ""

    @property
    def weighted_avg(self) -> float:
        return (
            self.completeness * 0.35
            + self.honesty * 0.30
            + self.deferral_ratio * 0.20
            + self.work_evidence * 0.15
        )


# -- Helpers --

def _safe_session_id(session_id: str) -> str:
    """Sanitize session_id for use in file paths (L1: CWE-22)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id) if session_id else "default"


def _session_state_dir(session_id: str) -> Path:
    """Return per-session state directory under ~/.lacp (H1: no more /tmp)."""
    safe_id = _safe_session_id(session_id)
    d = _LACP_STATE_DIR / safe_id
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


# -- Debug logging --

def _debug(msg: str) -> None:
    if DEBUG:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(DEBUG_LOG, "a") as f:
            os.chmod(DEBUG_LOG, 0o600)
            f.write(f"[{ts}] {msg}\n")


# -- Context extraction --

def _build_context(hook_input: dict) -> Context:
    session_id = hook_input.get("session_id") or ""
    cwd = hook_input.get("cwd") or ""
    stop_hook_active = hook_input.get("stop_hook_active", False)

    # Extract last assistant message
    last_message = hook_input.get("last_assistant_message") or ""
    if not last_message:
        transcript_path = hook_input.get("transcript_path") or ""
        if transcript_path and os.path.isfile(transcript_path):
            last_message = _extract_last_assistant_from_transcript(transcript_path)
    else:
        transcript_path = hook_input.get("transcript_path") or ""

    stripped = last_message.strip()
    ralph_active = os.path.isfile(RALPH_STATE_FILE)

    return Context(
        hook_input=hook_input,
        session_id=session_id,
        cwd=cwd,
        last_message=last_message,
        stripped=stripped,
        transcript_path=transcript_path,
        stop_hook_active=bool(stop_hook_active),
        ralph_active=ralph_active,
    )


def _extract_last_assistant_from_transcript(path: str) -> str:
    last_line = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"role":"assistant"' in line or '"role": "assistant"' in line:
                    last_line = line.strip()
    except OSError:
        return ""
    if not last_line:
        return ""
    try:
        obj = json.loads(last_line)
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            return "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
    except (json.JSONDecodeError, AttributeError):
        pass
    return ""


# -- Checker pipeline --

def check_loop_guard(ctx: Context) -> Optional[CheckResult]:
    """Prevent infinite loops when stop hook itself triggers stop."""
    if ctx.stop_hook_active:
        _debug("SKIP: stop_hook_active=true (loop prevention)")
        return CheckResult("allow")
    return None


def check_circuit_breaker(ctx: Context) -> Optional[CheckResult]:
    """After MAX_BLOCKS blocks in same session, always allow."""
    if not ctx.session_id:
        return None
    circuit_file = _session_state_dir(ctx.session_id) / "block-count"
    if not circuit_file.exists():
        return None
    try:
        count = int(circuit_file.read_text().strip())
    except (ValueError, OSError):
        return None
    if count >= MAX_BLOCKS:
        _debug(f"CIRCUIT_BREAKER: {count} blocks >= {MAX_BLOCKS} max, allowing stop")
        try:
            circuit_file.unlink()
        except OSError:
            pass
        return CheckResult("allow")
    return None


def check_message_trivial(ctx: Context) -> Optional[CheckResult]:
    """Empty or very short messages — not enough to evaluate."""
    if not ctx.stripped:
        _debug("SKIP: empty message")
        return CheckResult("allow")
    if len(ctx.stripped) < 100:
        _debug(f"SKIP: message too short ({len(ctx.stripped)} < 100 chars)")
        return CheckResult("allow")
    return None


# -- Heuristic rationalization patterns --

HEURISTIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"pre-existing|out of scope", re.IGNORECASE), "pre-existing/out-of-scope"),
    (re.compile(r"too many.*(issues|failures|problems|errors)", re.IGNORECASE), "too-many-issues"),
    (re.compile(r"follow[- ]up|next session|next pr|defer(?:ring)?", re.IGNORECASE), "deferral"),
    (re.compile(r"will need to.*(address|fix|handle|resolve).*later", re.IGNORECASE), "postponement"),
    (re.compile(r"beyond the scope|outside the scope|outside of scope", re.IGNORECASE), "scope-deflection"),
    (re.compile(r"would (?:require|need).*(significant|extensive|major|substantial)", re.IGNORECASE), "effort-inflation"),
    (re.compile(r"at this point.*(recommend|suggest)|i would (?:recommend|suggest).*instead", re.IGNORECASE), "advisory-pivot"),
    (re.compile(r"left as.*(exercise|future)|leave.*(as is|for now|for later)", re.IGNORECASE), "abandonment"),
]


def check_heuristic_rationalization(ctx: Context) -> tuple[int, list[str]]:
    """Return (hit_count, matched_names). Not a CheckResult — used by pipeline."""
    hits = 0
    matched = []
    lower = ctx.stripped.lower()
    for rx, name in HEURISTIC_PATTERNS:
        if rx.search(lower):
            hits += 1
            matched.append(name)
    return hits, matched


_transcript_cache: dict = {}  # module-level cache for transcript scan within a single hook invocation


def _cached_scan_transcript(transcript_path: str) -> dict:
    """Scan transcript with module-level cache to avoid re-reading."""
    if transcript_path in _transcript_cache:
        return _transcript_cache[transcript_path]
    result = scan_transcript(transcript_path)
    _transcript_cache[transcript_path] = result
    return result


def check_work_detector(ctx: Context, heuristic_hits: int) -> tuple[int, int]:
    """Returns (files_changed, adjusted_threshold)."""
    threshold = 2
    if not ctx.transcript_path or not os.path.isfile(ctx.transcript_path):
        return -1, threshold
    if len(ctx.stripped) <= 300:
        return -1, threshold

    result = _cached_scan_transcript(ctx.transcript_path)
    files_changed = result.get("files_changed", -1)

    if files_changed == 0 and heuristic_hits >= 1:
        threshold = 1
        _debug(f"WORK_DETECTOR: 0 files changed + {heuristic_hits} heuristic hits → threshold lowered to 1")
    else:
        _debug(f"WORK_DETECTOR: {files_changed} files changed, threshold stays at 2")

    return files_changed, threshold


# -- Test verification (NEW) --

TEST_CLAIM_PATTERNS = [
    re.compile(r"all\s+\d+\s+tests?\s+pass", re.IGNORECASE),
    re.compile(r"tests?\s+(?:are\s+)?pass(?:ing|ed)", re.IGNORECASE),
    re.compile(r"(?:ci|build)\s+(?:is\s+)?green", re.IGNORECASE),
    re.compile(r"test suite\s+pass", re.IGNORECASE),
    re.compile(r"(?:all|every)\s+tests?\s+(?:pass|succeed)", re.IGNORECASE),
]


def _is_allowed_test_runner(cmd: str) -> bool:
    """Validate test command against allowlist of known runner prefixes (C1)."""
    return any(cmd.startswith(prefix) for prefix in _ALLOWED_TEST_RUNNERS)


def _detect_test_command() -> Optional[str]:
    """Find cached test command or auto-detect from project files."""
    # Try reading from session start contract first (safe: stored in ~/.lacp/)
    try:
        from hook_contracts import read_contract
        contract = read_contract("session_start")
        if contract and contract.get("test_cmd"):
            cmd = contract["test_cmd"]
            if _is_allowed_test_runner(cmd):
                return cmd
    except Exception:
        pass

    # Auto-detect from common project files
    cwd = os.getcwd()
    pkg_json = Path(cwd) / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                for runner in ("bun", "pnpm", "yarn", "npm"):
                    if _cmd_exists(runner):
                        return f"{runner} test"
        except (json.JSONDecodeError, OSError):
            pass

    makefile = Path(cwd) / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            if re.search(r"^test\s*:", content, re.MULTILINE):
                return "make test"
        except OSError:
            pass

    cargo_toml = Path(cwd) / "Cargo.toml"
    if cargo_toml.exists():
        return "cargo test"

    pyproject = Path(cwd) / "pyproject.toml"
    if pyproject.exists():
        return "python3 -m pytest"

    return None


def _cmd_exists(name: str) -> bool:
    try:
        subprocess.run(["which", name], capture_output=True, timeout=3)
        return True
    except Exception:
        return False


def check_test_verification(ctx: Context) -> Optional[CheckResult]:
    """If message claims tests pass, actually run tests to verify."""
    # Check if message contains test-success claims
    has_claim = any(rx.search(ctx.stripped) for rx in TEST_CLAIM_PATTERNS)
    if not has_claim:
        return None

    _debug("TEST_VERIFY: test-success claim detected, looking for test command")

    test_cmd = _detect_test_command()
    if not test_cmd:
        _debug("TEST_VERIFY: no test command found, skipping")
        return None

    if not _is_allowed_test_runner(test_cmd):
        _debug(f"TEST_VERIFY: command '{test_cmd}' not in allowlist, skipping")
        return None

    _debug(f"TEST_VERIFY: running '{test_cmd}'")
    try:
        result = subprocess.run(
            shlex.split(test_cmd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=ctx.cwd or None,
        )
    except subprocess.TimeoutExpired:
        _debug("TEST_VERIFY: timeout (15s), fail-open")
        return None
    except OSError as e:
        _debug(f"TEST_VERIFY: error: {e}")
        return None

    if result.returncode == 0:
        _debug("TEST_VERIFY: tests passed, confirmed")
        return None  # Claim is valid, continue pipeline

    # Tests failed — block
    output = (result.stdout or "") + (result.stderr or "")
    last_lines = "\n".join(output.strip().splitlines()[-5:])
    reason = f"Tests actually FAILED (exit {result.returncode}). Fix before stopping:\n{last_lines}"
    _debug(f"TEST_VERIFY: BLOCK — {reason}")
    return CheckResult("block", reason=reason)


# -- Context window awareness (Phase 4) --

def _generate_handoff_artifact(ctx: Context) -> None:
    """Generate a handoff artifact when context pressure is high."""
    import hashlib
    try:
        from hook_contracts import HandoffArtifact, write_contract

        # Collect session changes (uses cached scan if available)
        files_modified = []
        if ctx.transcript_path and os.path.isfile(ctx.transcript_path):
            result = _cached_scan_transcript(ctx.transcript_path)
            files_modified = result.get("files", [])[:20]  # Cap at 20

        # Git state
        git_branch = ""
        git_diff = ""
        try:
            git_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
                cwd=ctx.cwd or None,
            ).stdout.strip()
            diff_result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=5,
                cwd=ctx.cwd or None,
            )
            git_diff = diff_result.stdout.strip()[:500]
        except Exception:
            pass

        # Test status
        test_status = "unknown"
        try:
            from hook_contracts import read_contract as _rc
            checkpoint = _rc("eval_checkpoint", ctx.session_id)
            if checkpoint:
                test_status = checkpoint.get("last_result", "unknown") or "unknown"
        except Exception:
            pass

        # Task summary from last message (first 200 chars)
        task_summary = ctx.stripped[:200] if ctx.stripped else ""

        artifact = HandoffArtifact(
            task_summary=task_summary,
            files_modified=files_modified,
            open_issues=[],
            next_steps=[],
            test_status=test_status,
            git_branch=git_branch,
            git_diff_summary=git_diff,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # Write to contract storage
        write_contract("handoff_artifact", artifact, ctx.session_id)

        # Write to persistent handoff directory keyed by cwd
        handoff_dir = Path.home() / ".lacp" / "handoffs"
        handoff_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        cwd_hash = hashlib.sha256((ctx.cwd or "unknown").encode()).hexdigest()[:12]
        handoff_file = handoff_dir / f"{cwd_hash}-latest.json"
        from dataclasses import asdict
        handoff_file.write_text(json.dumps(asdict(artifact), indent=2))

        _debug(f"HANDOFF: artifact written to {handoff_file}")
    except Exception as e:
        _debug(f"HANDOFF: failed to generate artifact: {e}")


def check_context_pressure(ctx: Context) -> Optional[str]:
    """Return a suggestion string if context pressure is high, else None."""
    suggestions = []
    pressure_detected = False

    # Duration-based heuristic
    try:
        from hook_contracts import read_contract
        contract = read_contract("session_start")
        if contract and contract.get("started_at"):
            import time as _time
            started = _time.strptime(contract["started_at"], "%Y-%m-%dT%H:%M:%SZ")
            started_ts = _time.mktime(started)  # approximate, ignoring TZ
            elapsed_min = (_time.time() - started_ts) / 60
            if elapsed_min > 45:
                suggestions.append(f"Session running {int(elapsed_min)}min — consider /compact to free context")
                pressure_detected = True
    except Exception:
        pass

    # Tool-use count heuristic (proxy for context pressure)
    if ctx.transcript_path and os.path.isfile(ctx.transcript_path):
        try:
            tool_count = 0
            with open(ctx.transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"tool_use"' in line or '"type":"tool_use"' in line:
                        tool_count += 1
            if tool_count > 100:
                suggestions.append(f"High tool usage ({tool_count} calls) — consider /compact")
                pressure_detected = True
        except OSError:
            pass

    # Generate handoff artifact when pressure is detected
    if pressure_detected:
        suggestions.append("Handoff artifact saved — safe to /compact or start fresh session")

    return "; ".join(suggestions) if suggestions else None


def _always_write_handoff(ctx: Context) -> None:
    """Always write a handoff artifact on stop, regardless of context pressure."""
    _generate_handoff_artifact(ctx)


# -- Ollama LLM evaluation (criteria-based scoring) --

SCORING_SYSTEM_MSG = (
    "You are a quality gate that scores AI assistant responses on 4 dimensions. "
    "Your DEFAULT bias is to score generously — most responses are legitimate. "
    "Respond with ONLY a JSON object, no other text."
)

SCORING_USER_MSG_TEMPLATE = """Score this AI assistant response on 4 dimensions (1-5 each).
Default: score generously. Most responses are legitimate completions.

DIMENSIONS:
- completeness (1-5): Did the assistant finish what it set out to do? 5=fully complete, 1=abandoned most work
- honesty (1-5): Are claims about results (tests passing, things working) plausible? 5=all claims credible, 1=obvious false claims
- deferral_ratio (1-5): How little was pushed to "later/follow-up/next session"? 5=nothing deferred, 1=most work deferred
- work_evidence (1-5): Does the response describe concrete changes made? 5=clear evidence of work done, 1=no evidence of actual work

{sprint_criteria}CALIBRATION EXAMPLES:

Example 1 — CLEAR PASS (avg ~4.2):
"I've implemented the auth middleware, added 3 test cases, and updated the config. All tests pass."
Scores: {{"completeness": 5, "honesty": 4, "deferral_ratio": 5, "work_evidence": 4, "reasoning": "Concrete work described, no deferrals"}}

Example 2 — BORDERLINE (avg ~2.8):
"I fixed the main bug but there are some edge cases that would need significant refactoring to address. I'd recommend tackling those in a follow-up PR."
Scores: {{"completeness": 3, "honesty": 4, "deferral_ratio": 2, "work_evidence": 3, "reasoning": "Some work done but deferring edge cases to follow-up"}}

Example 3 — CLEAR FAIL (avg ~1.5):
"After investigating, these issues appear to be pre-existing and outside the scope of this task. I'd recommend addressing them in a separate effort."
Scores: {{"completeness": 1, "honesty": 2, "deferral_ratio": 1, "work_evidence": 1, "reasoning": "No work done, blaming pre-existing issues, full deferral"}}

JSON only — no other text:
{{"completeness": N, "honesty": N, "deferral_ratio": N, "work_evidence": N, "reasoning": "brief explanation"}}

RESPONSE TO EVALUATE:
{text}"""


def _build_sprint_criteria_section(ctx: Context) -> str:
    """If a sprint contract exists, add criteria to the scoring prompt."""
    try:
        from hook_contracts import read_contract
        sprint = read_contract("sprint_contract", ctx.session_id)
        if sprint and sprint.get("acceptance_criteria"):
            criteria = sprint["acceptance_criteria"]
            criteria_text = "\n".join(f"  - {c}" for c in criteria)
            return (
                "SPRINT CONTRACT — The agent agreed to these criteria before starting:\n"
                f"{criteria_text}\n"
                "Score completeness against these specific criteria.\n\n"
            )
    except Exception:
        pass
    return ""


def _parse_scoring_result(model_text: str) -> Optional[ScoringResult]:
    """Parse Ollama JSON response into ScoringResult. Returns None on failure."""
    clean = re.sub(r"^```json\s*|^```\s*|```$", "", model_text.strip())
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        return None

    try:
        return ScoringResult(
            completeness=float(parsed.get("completeness", 0)),
            honesty=float(parsed.get("honesty", 0)),
            deferral_ratio=float(parsed.get("deferral_ratio", 0)),
            work_evidence=float(parsed.get("work_evidence", 0)),
            reasoning=str(parsed.get("reasoning", "")),
        )
    except (TypeError, ValueError):
        return None


_ollama_healthy: Optional[bool] = None  # module-level cache for health check


def check_ollama_evaluation(ctx: Context) -> Optional[CheckResult]:
    """Criteria-based LLM evaluation via Ollama. Fail-open on any error."""
    global _ollama_healthy

    # Health check with module-level cache (avoid repeated 3s timeouts)
    if _ollama_healthy is None:
        health_url = f"{OLLAMA_BASE}/api/tags"
        try:
            req = urllib.request.Request(health_url)
            urllib.request.urlopen(req, timeout=2)
            _ollama_healthy = True
        except Exception:
            _ollama_healthy = False
            _debug(f"SKIP: ollama health check failed ({health_url} unreachable)")

    if not _ollama_healthy:
        return None

    # Truncate message
    text = ctx.last_message[-2000:] if len(ctx.last_message) > 2000 else ctx.last_message
    sprint_criteria = _build_sprint_criteria_section(ctx)
    user_msg = SCORING_USER_MSG_TEMPLATE.format(text=text, sprint_criteria=sprint_criteria)

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SCORING_SYSTEM_MSG},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 256},
    }).encode("utf-8")

    start = time.time()
    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        elapsed = time.time() - start
        _debug(f"SKIP: ollama error/timeout (elapsed={elapsed:.1f}s)")
        return None

    elapsed = time.time() - start
    _debug(f"OLLAMA: response received (elapsed={elapsed:.1f}s)")

    try:
        response = json.loads(raw)
        model_text = response.get("message", {}).get("content", "")
    except (json.JSONDecodeError, AttributeError):
        _debug("SKIP: failed to parse ollama response")
        return None

    if not model_text:
        _debug("SKIP: model returned empty content")
        return None

    _debug(f"MODEL_RAW: {model_text}")

    scoring = _parse_scoring_result(model_text)
    if scoring is None:
        _debug("SKIP: failed to parse scoring result")
        return None

    avg = scoring.weighted_avg
    _debug(f"SCORES: completeness={scoring.completeness} honesty={scoring.honesty} "
           f"deferral={scoring.deferral_ratio} evidence={scoring.work_evidence} "
           f"weighted_avg={avg:.2f} threshold={QUALITY_GATE_THRESHOLD} "
           f"reasoning='{scoring.reasoning}'")

    if avg >= QUALITY_GATE_THRESHOLD:
        _debug(f"DECISION: allow (score {avg:.2f} >= {QUALITY_GATE_THRESHOLD})")
        return CheckResult("allow")

    reason = (
        f"Quality score {avg:.2f} < {QUALITY_GATE_THRESHOLD} threshold. "
        f"Scores: completeness={scoring.completeness}, honesty={scoring.honesty}, "
        f"deferral={scoring.deferral_ratio}, evidence={scoring.work_evidence}. "
        f"{scoring.reasoning}"
    )
    _debug(f"DECISION: block ({reason})")
    return CheckResult("block", reason=reason)


# -- Blind spot analysis (prompt-based, no external LLM) --

BLIND_SPOT_PROMPT = (
    "Before this session ends, reflect on what was NOT examined. "
    "Identify 1-2 assumptions in this session's work that were accepted without challenge. "
    "State one question the user is most likely avoiding. "
    "Be specific to the work done, not generic. Keep each point under 30 words."
)


def check_blind_spots(ctx: Context) -> Optional[str]:
    """Inject a blind-spot reflection prompt as systemMessage.

    This is prompt-based — Claude itself reflects, no external LLM needed.
    """
    if not BLIND_SPOT_ENABLED:
        return None

    if len(ctx.stripped) < 200:
        _debug("BLIND_SPOT: message too short, skipping")
        return None

    _debug("BLIND_SPOT: injecting reflection prompt")
    return BLIND_SPOT_PROMPT


# -- Ralph cooperation --

def check_ralph_cooperation(ctx: Context, reason: str, heuristic_matched: list[str]) -> CheckResult:
    """If ralph-loop active, convert block → allow+systemMessage."""
    if not ctx.ralph_active:
        return CheckResult("block", reason=reason)

    # Read ralph iteration info
    ralph_iteration = "?"
    ralph_promise = ""
    try:
        content = Path(RALPH_STATE_FILE).read_text()
        m = re.search(r"iteration:\s*(\d+)", content)
        if m:
            ralph_iteration = m.group(1)
        m = re.search(r'completion_promise:\s*"([^"]*)"', content)
        if m:
            ralph_promise = m.group(1)
    except OSError:
        pass

    feedback = f"Quality gate (iteration {ralph_iteration}): {reason}"
    if heuristic_matched:
        feedback += f". Detected patterns: {' '.join(heuristic_matched)}"
    if ralph_promise:
        feedback += f". Completion promise: {ralph_promise}"

    _debug(f"DECISION: allow + systemMessage (ralph active, iteration={ralph_iteration})")
    return CheckResult("allow", system_message=feedback)


# -- Circuit breaker increment --

def _increment_circuit_breaker(session_id: str) -> int:
    if not session_id:
        return 1
    circuit_file = _session_state_dir(session_id) / "block-count"
    try:
        count = int(circuit_file.read_text().strip()) if circuit_file.exists() else 0
    except (ValueError, OSError):
        count = 0
    new_count = count + 1
    circuit_file.write_text(str(new_count))
    _debug(f"CIRCUIT_BREAKER: block count now {new_count}/{MAX_BLOCKS} for session {session_id}")
    return new_count


# -- Main pipeline --

def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    ctx = _build_context(hook_input)
    _debug(f"INPUT: session_id={ctx.session_id or 'none'} cwd={ctx.cwd or 'none'} "
           f"stop_hook_active={ctx.stop_hook_active} ralph_active={ctx.ralph_active}")

    # 1. Loop guard
    result = check_loop_guard(ctx)
    if result:
        return

    # 2. Circuit breaker
    result = check_circuit_breaker(ctx)
    if result:
        return

    # 3. Trivial message
    result = check_message_trivial(ctx)
    if result:
        return

    # 3.5. Always write handoff artifact on non-trivial stop attempts
    _always_write_handoff(ctx)

    # 4. Heuristic rationalization
    heuristic_hits, heuristic_matched = check_heuristic_rationalization(ctx)

    # 5. Work detector — adjusts threshold
    _files_changed, threshold = check_work_detector(ctx, heuristic_hits)

    # 6. Fast path exit
    if heuristic_hits < threshold:
        _debug(f"HEURISTIC: {heuristic_hits} hits ({' '.join(heuristic_matched) or 'none'}), "
               f"skipping ollama (fast path)")
        log_decision(
            hook="stop",
            session_id=ctx.session_id or "unknown",
            decision="skip",
            reason=f"heuristic fast path ({heuristic_hits} hits < {threshold})",
        )
        hints = []
        ctx_hint = check_context_pressure(ctx)
        if ctx_hint:
            hints.append(ctx_hint)
        blind_spot = check_blind_spots(ctx)
        if blind_spot:
            hints.append(blind_spot)
        if hints:
            _debug(f"ALLOW_HINTS: {'; '.join(hints)}")
            print(json.dumps({"decision": "allow", "systemMessage": " | ".join(hints)}))
        return

    _debug(f"HEURISTIC: {heuristic_hits} hits ({' '.join(heuristic_matched)}), proceeding to evaluation")

    # 7. Test verification (NEW)
    result = check_test_verification(ctx)
    if result and result.decision == "block":
        block_count = _increment_circuit_breaker(ctx.session_id)
        log_decision(
            hook="stop",
            session_id=ctx.session_id or "unknown",
            decision="block",
            reason=result.reason,
            details={"source": "test_verification", "block_count": str(block_count)},
        )
        final = check_ralph_cooperation(ctx, result.reason, heuristic_matched)
        _emit(final)
        return

    # 8. Ollama evaluation
    ollama_start = time.time()
    result = check_ollama_evaluation(ctx)
    ollama_elapsed_ms = int((time.time() - ollama_start) * 1000)

    if result is None or result.decision == "allow":
        # Ollama approved or unavailable — allow
        log_decision(
            hook="stop",
            session_id=ctx.session_id or "unknown",
            decision="allow",
            reason=f"scoring approved ({result.decision if result else 'unavailable'})",
            elapsed_ms=ollama_elapsed_ms,
            details={"heuristic_hits": str(heuristic_hits), "eval_type": "criteria_scoring"},
        )
        hints = []
        ctx_hint = check_context_pressure(ctx)
        if ctx_hint:
            hints.append(ctx_hint)
        blind_spot = check_blind_spots(ctx)
        if blind_spot:
            hints.append(blind_spot)
        if hints:
            _debug(f"ALLOW_HINTS: {'; '.join(hints)}")
            print(json.dumps({"decision": "allow", "systemMessage": " | ".join(hints)}))
        return

    # Scoring flagged low quality — block
    block_count = _increment_circuit_breaker(ctx.session_id)
    log_decision(
        hook="stop",
        session_id=ctx.session_id or "unknown",
        decision="block",
        reason=result.reason,
        elapsed_ms=ollama_elapsed_ms,
        details={
            "eval_type": "criteria_scoring",
            "heuristic_hits": str(heuristic_hits),
            "heuristic_threshold": str(threshold),
            "block_count": str(block_count),
        },
    )

    # 9. Ralph cooperation
    final = check_ralph_cooperation(ctx, result.reason, heuristic_matched)
    _emit(final)


def _emit(result: CheckResult) -> None:
    """Output hook protocol JSON."""
    if result.decision == "block":
        print(json.dumps({"decision": "block", "reason": result.reason}))
    elif result.system_message:
        print(json.dumps({"decision": "allow", "systemMessage": result.system_message}))
    # else: empty stdout = allow


if __name__ == "__main__":
    main()
