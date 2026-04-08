#!/usr/bin/env python3
"""LACP Agent-to-Agent (A2A) Messaging — file-based inter-agent communication.

Implements a lightweight A2A protocol for LACP agent teams, inspired by
Claude Code's team messaging and the A2A protocol (arXiv:2601.13671).

Messages are JSONL files in ~/.lacp/messages/ — one file per conversation thread.
Each agent polls for new messages or uses filesystem watchers.

Usage:
    from agent_messaging import send_message, receive_messages, broadcast

    send_message(from_agent="lead", to_agent="executor", content="implement auth module")
    messages = receive_messages(agent_id="executor")
    broadcast(from_agent="lead", content="all tests passing, proceed to deploy")

CLI:
    python3 agent_messaging.py send --from lead --to executor "implement auth"
    python3 agent_messaging.py receive --agent executor
    python3 agent_messaging.py broadcast --from lead "tests passing"
    python3 agent_messaging.py threads --agent executor
    python3 agent_messaging.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MESSAGES_DIR = Path.home() / ".lacp" / "messages"
THREADS_DIR = MESSAGES_DIR / "threads"
BROADCAST_FILE = MESSAGES_DIR / "broadcast.jsonl"


@dataclass
class Message:
    id: str
    thread_id: str
    from_agent: str
    to_agent: str           # "all" for broadcasts
    content: str
    timestamp: str
    message_type: str = "text"  # text, task, result, status
    metadata: dict[str, Any] = field(default_factory=dict)
    read: bool = False


def _generate_id() -> str:
    return f"msg-{int(time.time() * 1000)}-{os.getpid()}"


def _thread_file(from_agent: str, to_agent: str) -> Path:
    """Get the thread file path for a conversation between two agents."""
    pair = "-".join(sorted([from_agent, to_agent]))
    return THREADS_DIR / f"{pair}.jsonl"


def send_message(
    from_agent: str,
    to_agent: str,
    content: str,
    message_type: str = "text",
    metadata: dict[str, Any] | None = None,
) -> Message:
    """Send a message from one agent to another."""
    THREADS_DIR.mkdir(parents=True, exist_ok=True)

    thread_file = _thread_file(from_agent, to_agent)
    thread_id = thread_file.stem

    msg = Message(
        id=_generate_id(),
        thread_id=thread_id,
        from_agent=from_agent,
        to_agent=to_agent,
        content=content,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        message_type=message_type,
        metadata=metadata or {},
    )

    with thread_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(msg)) + "\n")

    return msg


def broadcast(
    from_agent: str,
    content: str,
    message_type: str = "text",
    metadata: dict[str, Any] | None = None,
) -> Message:
    """Broadcast a message to all agents."""
    MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

    msg = Message(
        id=_generate_id(),
        thread_id="broadcast",
        from_agent=from_agent,
        to_agent="all",
        content=content,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        message_type=message_type,
        metadata=metadata or {},
    )

    with BROADCAST_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(msg)) + "\n")

    return msg


def receive_messages(
    agent_id: str,
    since: str = "",
    unread_only: bool = True,
    limit: int = 50,
) -> list[Message]:
    """Receive messages for a specific agent (from threads + broadcasts)."""
    messages: list[Message] = []

    # Direct messages from thread files
    if THREADS_DIR.exists():
        for thread_file in THREADS_DIR.glob("*.jsonl"):
            if agent_id not in thread_file.stem:
                continue
            try:
                for line in thread_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("to_agent") == agent_id or data.get("to_agent") == "all":
                        if since and data.get("timestamp", "") <= since:
                            continue
                        msg = Message(**{k: data[k] for k in Message.__dataclass_fields__ if k in data})
                        messages.append(msg)
            except (json.JSONDecodeError, OSError):
                continue

    # Broadcasts
    if BROADCAST_FILE.exists():
        try:
            for line in BROADCAST_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("from_agent") == agent_id:
                    continue  # skip own broadcasts
                if since and data.get("timestamp", "") <= since:
                    continue
                msg = Message(**{k: data[k] for k in Message.__dataclass_fields__ if k in data})
                messages.append(msg)
        except (json.JSONDecodeError, OSError):
            pass

    # Sort by timestamp, newest first
    messages.sort(key=lambda m: m.timestamp, reverse=True)
    return messages[:limit]


def list_threads(agent_id: str = "") -> list[dict[str, Any]]:
    """List all active threads, optionally filtered by agent."""
    threads = []
    if THREADS_DIR.exists():
        for thread_file in sorted(THREADS_DIR.glob("*.jsonl")):
            if agent_id and agent_id not in thread_file.stem:
                continue
            try:
                lines = thread_file.read_text(encoding="utf-8").splitlines()
                msg_count = len([l for l in lines if l.strip()])
                last_msg = ""
                if lines:
                    for line in reversed(lines):
                        if line.strip():
                            data = json.loads(line)
                            last_msg = data.get("content", "")[:80]
                            break
                threads.append({
                    "thread_id": thread_file.stem,
                    "messages": msg_count,
                    "last_message": last_msg,
                    "file": str(thread_file),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return threads


def cleanup_old_messages(max_age_hours: int = 48) -> int:
    """Remove messages older than max_age_hours."""
    cutoff = time.time() - (max_age_hours * 3600)
    cleaned = 0

    if THREADS_DIR.exists():
        for thread_file in THREADS_DIR.glob("*.jsonl"):
            try:
                if thread_file.stat().st_mtime < cutoff:
                    thread_file.unlink()
                    cleaned += 1
            except OSError:
                continue

    if BROADCAST_FILE.exists():
        try:
            if BROADCAST_FILE.stat().st_mtime < cutoff:
                BROADCAST_FILE.unlink()
                cleaned += 1
        except OSError:
            pass

    return cleaned


def _self_test() -> None:
    """Test A2A messaging with temp directory."""
    import tempfile
    global MESSAGES_DIR, THREADS_DIR, BROADCAST_FILE

    old_dirs = (MESSAGES_DIR, THREADS_DIR, BROADCAST_FILE)
    with tempfile.TemporaryDirectory() as tmp:
        MESSAGES_DIR = Path(tmp)
        THREADS_DIR = MESSAGES_DIR / "threads"
        BROADCAST_FILE = MESSAGES_DIR / "broadcast.jsonl"

        # Send message
        msg = send_message("lead", "executor", "implement auth module", message_type="task")
        assert msg.from_agent == "lead"
        assert msg.to_agent == "executor"

        # Receive as executor
        msgs = receive_messages("executor")
        assert len(msgs) == 1
        assert msgs[0].content == "implement auth module"

        # Lead shouldn't see their own sent message via receive
        lead_msgs = receive_messages("lead")
        # Lead sees the message because they're in the thread
        assert len(lead_msgs) == 0  # to_agent is executor, not lead

        # Broadcast
        broadcast("lead", "all tests passing", message_type="status")
        executor_msgs = receive_messages("executor")
        assert any(m.content == "all tests passing" for m in executor_msgs)

        # Threads
        threads = list_threads("executor")
        assert len(threads) >= 1

        # Cleanup
        cleaned = cleanup_old_messages(max_age_hours=0)
        # Nothing to clean (just created)

    MESSAGES_DIR, THREADS_DIR, BROADCAST_FILE = old_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="LACP Agent-to-Agent Messaging")
    sub = parser.add_subparsers(dest="command")

    send_p = sub.add_parser("send")
    send_p.add_argument("--from", dest="from_agent", required=True)
    send_p.add_argument("--to", dest="to_agent", required=True)
    send_p.add_argument("--type", default="text")
    send_p.add_argument("content", nargs="+")

    recv_p = sub.add_parser("receive")
    recv_p.add_argument("--agent", required=True)
    recv_p.add_argument("--since", default="")
    recv_p.add_argument("--limit", type=int, default=20)

    bcast_p = sub.add_parser("broadcast")
    bcast_p.add_argument("--from", dest="from_agent", required=True)
    bcast_p.add_argument("--type", default="text")
    bcast_p.add_argument("content", nargs="+")

    thread_p = sub.add_parser("threads")
    thread_p.add_argument("--agent", default="")

    sub.add_parser("cleanup")

    parser.add_argument("--self-test", action="store_true")

    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if args.command == "send":
        msg = send_message(args.from_agent, args.to_agent, " ".join(args.content), args.type)
        print(json.dumps(asdict(msg), indent=2))

    elif args.command == "receive":
        msgs = receive_messages(args.agent, since=args.since, limit=args.limit)
        for m in msgs:
            print(f"[{m.timestamp[:19]}] {m.from_agent} → {m.to_agent}: {m.content[:100]}")

    elif args.command == "broadcast":
        msg = broadcast(args.from_agent, " ".join(args.content), args.type)
        print(json.dumps(asdict(msg), indent=2))

    elif args.command == "threads":
        threads = list_threads(args.agent)
        for t in threads:
            print(f"  {t['thread_id']:30s} {t['messages']:>4d} msgs  {t['last_message'][:50]}")

    elif args.command == "cleanup":
        cleaned = cleanup_old_messages()
        print(f"Cleaned {cleaned} old message files")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
