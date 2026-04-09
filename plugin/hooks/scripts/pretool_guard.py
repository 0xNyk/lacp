#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

BLOCKS = [
    (re.compile(r"\b(?:npm|yarn|pnpm|cargo)\s+publish\b", re.IGNORECASE), "BLOCKED: Publishing to registry requires explicit user approval. Ask the user first."),
    (re.compile(r"\b(?:curl|wget)\b.*\|\s*(?:python3?|node|ruby|perl)\b", re.IGNORECASE), "BLOCKED: Piping network content to an interpreter is unsafe. Download first, review, then run."),
    (re.compile(r"\bchmod\s+(?:-R\s+)?777\b"), "BLOCKED: chmod 777 is overly permissive. Use specific permissions (e.g. 755, 644)."),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "BLOCKED: git reset --hard is destructive. Ask the user first."),
    (re.compile(r"\bgit\s+clean\s+-f", re.IGNORECASE), "BLOCKED: git clean -f is destructive. Ask the user first."),
    (re.compile(r"\bdocker\s+run\b[^\n\r]*--privileged\b", re.IGNORECASE), "BLOCKED: docker run --privileged is a security risk. Use specific capabilities instead."),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "BLOCKED: Fork bomb detected."),
    (re.compile(r"\b(?:scp|rsync)\b.*\s/root(?:/|\s|$)", re.IGNORECASE), "BLOCKED: scp/rsync to /root is restricted. Use a non-root target path."),
]

PROTECTED_PATHS = re.compile(r"(\.env($|\.)|config\.toml($|\.)|secrets?|\.claude/settings\.json$|authorized_keys$|\.(pem|key)$|(^|/)\.gnupg(/|$))", re.IGNORECASE)

MUTATING_LOCAL_PATTERNS = [
    re.compile(r"\b(?:python(?:3)?\s+-m\s+venv|uv\s+venv|virtualenv)\b", re.IGNORECASE),
    re.compile(r"\b(?:pip(?:3)?\s+install|poetry\s+install|npm\s+install|pnpm\s+install|yarn\s+install)\b", re.IGNORECASE),
    re.compile(r"\b(?:apt(?:-get)?\s+install|brew\s+install)\b", re.IGNORECASE),
]

HOOKS_DIR = Path.home() / ".claude" / "hooks"
DEFAULT_TTL_SECONDS = 12 * 3600


def _scope_id() -> str:
    # Explicit scope wins.
    explicit = os.getenv("CLAUDE_CONTEXT_SCOPE", "").strip()
    if explicit:
        return explicit

    # Use per-window/per-pane IDs when present.
    for key in ("TMUX_PANE", "WEZTERM_PANE", "ITERM_SESSION_ID", "TERM_SESSION_ID", "WINDOWID"):
        val = os.getenv(key, "").strip()
        if val:
            return f"{key}:{val}"

    # Fallback to current working directory hash.
    cwd = os.getcwd()
    digest = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:12]
    return f"cwd:{digest}"


def _state_path() -> Path:
    safe = re.sub(r"[^A-Za-z0-9._:-]", "_", _scope_id())
    return HOOKS_DIR / f".remote_context.{safe}.json"


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _get_command(payload: dict) -> str:
    return str(payload.get("tool_input", {}).get("command") or "")


def _get_path(payload: dict) -> str:
    p = str(payload.get("tool_input", {}).get("file_path") or "")
    if not p:
        return ""
    try:
        return str(Path(p).expanduser())
    except Exception:
        return p


_PUSH_MAIN_RE = re.compile(r"\bgit\s+push\b[^\n\r]*(?:\bmain\b|\bmaster\b)", re.IGNORECASE)
_REPO_VISIBILITY_CACHE: dict[str, bool] = {}  # remote_url -> is_private


def _is_push_to_main(cmd: str) -> bool:
    return bool(_PUSH_MAIN_RE.search(cmd))


def _is_repo_private() -> bool:
    """Check if current repo is private. Returns True (allow push) if private or unknown."""
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return True  # Can't determine — allow

    if remote in _REPO_VISIBILITY_CACHE:
        return _REPO_VISIBILITY_CACHE[remote]

    # Check cache file to avoid repeated gh calls
    cache_file = Path.home() / ".claude" / "hooks" / ".repo_visibility_cache.json"
    try:
        cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    except Exception:
        cache = {}

    if remote in cache:
        _REPO_VISIBILITY_CACHE[remote] = cache[remote]
        return cache[remote]

    # Query GitHub API via gh
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "isPrivate", "-q", ".isPrivate"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            is_private = result.stdout.strip().lower() == "true"
            _REPO_VISIBILITY_CACHE[remote] = is_private
            cache[remote] = is_private
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, indent=2) + "\n")
            return is_private
    except Exception:
        pass

    return True  # Default: allow (assume private if can't check)


def _is_rm_rf(cmd: str) -> bool:
    try:
        argv = shlex.split(cmd)
    except Exception:
        return False
    if not argv or argv[0] != "rm":
        return False

    recursive = False
    force = False
    for token in argv[1:]:
        if token == "--":
            break
        if token.startswith("--"):
            if token == "--recursive":
                recursive = True
            elif token == "--force":
                force = True
            continue
        if not token.startswith("-"):
            continue
        flags = token[1:]
        if "r" in flags or "R" in flags:
            recursive = True
        if "f" in flags:
            force = True

    return recursive and force


def _is_mutating_local_setup(cmd: str) -> bool:
    return any(rx.search(cmd) for rx in MUTATING_LOCAL_PATTERNS)


def _parse_ssh_host(cmd: str) -> str:
    try:
        argv = shlex.split(cmd)
    except Exception:
        return ""
    if not argv or argv[0] != "ssh":
        return ""
    for tok in argv[1:]:
        if tok.startswith("-"):
            continue
        host = tok.split("@", 1)[-1]
        if host:
            return host
        return ""
    return ""


def _is_ssh_to_host(cmd: str, host: str) -> bool:
    parsed = _parse_ssh_host(cmd)
    return parsed.lower() == host.lower() if parsed and host else False


def _state_read() -> dict:
    path = _state_path()
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _state_write(host: str, source: str = "auto") -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "host": host,
        "source": source,
        "scope": _scope_id(),
        "state_file": str(path),
        "updated_at_epoch": int(time.time()),
        "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "local_hostname": socket.gethostname(),
        "cwd": os.getcwd(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _resolve_remote_lock_host(cmd: str) -> str:
    explicit = os.getenv("CLAUDE_REMOTE_LOCK_HOST", "").strip()
    if explicit:
        return explicit

    ssh_host = _parse_ssh_host(cmd)
    if ssh_host:
        _state_write(ssh_host, source="auto:ssh_command")
        return ssh_host

    auto_enabled = os.getenv("CLAUDE_REMOTE_LOCK_AUTO", "1").strip().lower() not in {"0", "false", "no"}
    if not auto_enabled:
        return ""

    state = _state_read()
    host = str(state.get("host") or "").strip()
    updated = int(state.get("updated_at_epoch") or 0)
    ttl = int(os.getenv("CLAUDE_REMOTE_LOCK_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)) or DEFAULT_TTL_SECONDS)
    if host and updated and (int(time.time()) - updated) <= ttl:
        return host
    return ""


def run_bash_guard(payload: dict) -> int:
    cmd = _get_command(payload)

    if re.search(r'\bgit\s+commit\b', cmd, re.IGNORECASE) and \
       re.search(r'co-authored-by', cmd, re.IGNORECASE):
        print("BLOCKED: Co-authoring trailers not allowed in commits.", file=sys.stderr)
        return 2

    if _is_rm_rf(cmd):
        print("BLOCKED: Use trash instead of rm -rf", file=sys.stderr)
        return 2

    remote_lock_host = _resolve_remote_lock_host(cmd)
    allow_local = os.getenv("CLAUDE_REMOTE_LOCK_ALLOW_LOCAL", "").strip().lower() in {"1", "true", "yes"}
    if remote_lock_host and _is_mutating_local_setup(cmd) and not _is_ssh_to_host(cmd, remote_lock_host) and not allow_local:
        print(
            f"BLOCKED: remote lock active for host '{remote_lock_host}' in scope '{_scope_id()}'. "
            f"Run mutating setup commands via 'ssh {remote_lock_host} ...' or unlock this scope.",
            file=sys.stderr,
        )
        return 2

    # Push-to-main guard: block only for public repos
    if _is_push_to_main(cmd) and not _is_repo_private():
        print("BLOCKED: Public repo — use feature branches, not direct push to main/master", file=sys.stderr)
        return 2

    for rx, msg in BLOCKS:
        if rx.search(cmd):
            print(msg, file=sys.stderr)
            return 2

    # Network exfiltration guard (defense-in-depth: catches curl/wget --data patterns
    # but is bypassable via nc, python3 -c, base64 encoding, etc. — not a security boundary)
    if re.search(r"\b(?:curl|wget)\b.*(?:-d|--data|--data-binary)\s+@[^\s]*(?:\.env|\.ssh|credentials|\.key|\.pem|secrets)", cmd, re.IGNORECASE):
        print("BLOCKED: potential data exfiltration from sensitive file", file=sys.stderr)
        return 2

    # Optional LLM classifier for ambiguous commands (Anthropic auto-mode pattern)
    # Two-stage: regex passed → check if command needs contextual review → Ollama classifies
    if os.getenv("LACP_PRETOOL_CLASSIFIER_ENABLED", "0") == "1":
        result = _llm_classify_command(cmd, payload)
        if result == 2:
            return 2

    return 0


# Patterns that passed regex but warrant contextual LLM review
_NEEDS_REVIEW_PATTERNS = [
    re.compile(r"\bcurl\b.*(?:-X\s+(?:POST|PUT|DELETE|PATCH)|-d\s)", re.IGNORECASE),
    re.compile(r"\bdocker\s+run\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+(?:exec|run)\b.*--", re.IGNORECASE),
    re.compile(r"\bchmod\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
]


def _llm_classify_command(cmd: str, payload: dict) -> int:
    """Classify ambiguous commands via local Ollama (auto-mode pattern).

    Key insight from Anthropic: strip assistant messages to prevent self-persuasion.
    Only evaluate the command itself in context of cwd/branch.
    Returns 0 (allow) or 2 (block). Fail-open on any error.
    """
    import urllib.request
    import urllib.error

    # Only classify commands matching review patterns
    if not any(rx.search(cmd) for rx in _NEEDS_REVIEW_PATTERNS):
        return 0

    ollama_url = os.getenv("LACP_QUALITY_GATE_URL", "http://localhost:11434/api/chat")
    ollama_model = os.getenv("LACP_QUALITY_GATE_MODEL", "llama3.1:8b")

    cwd = payload.get("cwd", "")
    # Intentionally do NOT include assistant message (auto-mode insight: prevent self-persuasion)
    prompt = (
        f"Is this shell command safe to run autonomously?\n"
        f"Command: {cmd}\n"
        f"Working directory: {cwd}\n\n"
        f"Answer ONLY with JSON: {{\"safe\": true}} or {{\"safe\": false, \"reason\": \"...\"}}\n"
        f"Default: safe=true. Block ONLY if the command could destroy data, exfiltrate secrets, "
        f"or affect systems outside the working directory."
    )

    body = json.dumps({
        "model": ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False, "format": "json",
        "options": {"temperature": 0, "num_predict": 64},
    }).encode()

    try:
        req = urllib.request.Request(ollama_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            raw = json.loads(resp.read().decode())
        text = raw.get("message", {}).get("content", "")
        parsed = json.loads(re.sub(r"^```json\s*|```$", "", text.strip()))
        if parsed.get("safe") is False:
            reason = parsed.get("reason", "LLM classifier flagged as unsafe")
            print(f"BLOCKED (classifier): {reason}", file=sys.stderr)
            return 2
    except Exception:
        pass  # Fail-open: any error → allow

    return 0


def run_write_guard(payload: dict) -> int:
    p = _get_path(payload)
    if p and PROTECTED_PATHS.search(p):
        print("Blocked: protected file", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    payload = _read_payload()

    if mode == "bash":
        return run_bash_guard(payload)
    if mode == "write":
        return run_write_guard(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
