#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

VAULT = Path('/Users/nyk/obsidian/nyk')
DAILY_DIR = VAULT / '00-home' / 'daily'
STATE = Path.home() / '.lacp' / 'cache' / 'agent-daily-activity-state.json'
CLAUDE_TELEMETRY = Path.home() / '.local' / 'share' / 'claude-hooks' / 'telemetry.jsonl'
HERMES_SESSIONS = Path.home() / '.hermes' / 'sessions'


def now_local():
    return datetime.now().astimezone()


def today_path(ts: datetime) -> Path:
    return DAILY_DIR / f"{ts.date().isoformat()}.md"


def ensure_agent_daily_section(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {path.stem}\n\n## Agent Daily\n\n")
        return
    txt = path.read_text()
    if '## Agent Daily' not in txt:
        if not txt.endswith('\n'):
            txt += '\n'
        txt += '\n## Agent Daily\n\n'
        path.write_text(txt)


def append_line(path: Path, line: str):
    txt = path.read_text()
    marker = '## Agent Daily'
    idx = txt.find(marker)
    if idx == -1:
        txt += '\n## Agent Daily\n\n'
        idx = txt.find(marker)
    after = txt[idx:]
    if line in after:
        return False
    insert_at = idx + len(marker)
    while insert_at < len(txt) and txt[insert_at] in '\r\n':
        insert_at += 1
    prefix = txt[:insert_at]
    rest = txt[insert_at:]
    if prefix and not prefix.endswith('\n'):
        prefix += '\n'
    new_txt = prefix + line + '\n' + rest
    path.write_text(new_txt)
    return True


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + '\n')


def record_agent(agent: str, note: str):
    ts = now_local()
    p = today_path(ts)
    ensure_agent_daily_section(p)
    line = f"- [{ts.strftime('%H:%M')}] {agent}: {note}"
    changed = append_line(p, line)
    return {'path': str(p), 'line': line, 'changed': changed}


def claude_stop():
    cwd = os.getcwd()
    return record_agent('Claude', f"session stop in `{cwd}`")


def hermes_poll():
    state = load_state()
    last = float(state.get('hermes_last_mtime', 0))
    latest = None
    if HERMES_SESSIONS.exists():
        for p in HERMES_SESSIONS.glob('session_*.json'):
            try:
                mt = p.stat().st_mtime
            except Exception:
                continue
            if mt > last and (latest is None or mt > latest[1]):
                latest = (p, mt)
    if latest is None:
        return {'changed': False, 'reason': 'no_new_hermes_session'}
    p, mt = latest
    ts = datetime.fromtimestamp(mt).astimezone()
    daily = today_path(ts)
    ensure_agent_daily_section(daily)
    line = f"- [{ts.strftime('%H:%M')}] Hermes: session activity `{p.name}`"
    changed = append_line(daily, line)
    state['hermes_last_mtime'] = mt
    save_state(state)
    return {'changed': changed, 'path': str(daily), 'line': line}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['claude-stop', 'hermes-poll'])
    args = ap.parse_args()
    if args.mode == 'claude-stop':
        out = claude_stop()
    else:
        out = hermes_poll()
    print(json.dumps({'ok': True, **out}, indent=2))


if __name__ == '__main__':
    main()
