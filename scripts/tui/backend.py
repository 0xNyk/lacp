"""LACP TUI backend — async subprocess runner for bin/ commands."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


def _lacp_root() -> str:
    """Resolve LACP repo root from this file's location."""
    return str(Path(__file__).resolve().parent.parent.parent)


class LacpBackend:
    """Async interface to LACP CLI commands via --json output."""

    def __init__(self) -> None:
        self.root = _lacp_root()

    async def _run(self, *args: str) -> dict:
        """Run a bin/ command, parse JSON stdout.

        Handles non-zero exit codes gracefully — commands like lacp-doctor
        exit 1 on failures but still emit valid JSON.
        """
        cmd = list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "LACP_ROOT": self.root},
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
        except asyncio.TimeoutError:
            return {"ok": False, "error": "command timed out after 60s"}
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {cmd[0]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        raw = stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace").strip()
                return {"ok": False, "error": err or f"exit code {proc.returncode}"}
            return {"ok": True}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Some commands emit multiple JSON objects; try first line
            first_line = raw.split("\n", 1)[0].strip()
            if first_line:
                try:
                    return json.loads(first_line)
                except json.JSONDecodeError:
                    pass
            return {"ok": False, "error": f"invalid JSON: {raw[:200]}"}

    def _bin(self, name: str) -> str:
        return os.path.join(self.root, "bin", name)

    async def doctor(self, with_hints: bool = False) -> dict:
        args = [self._bin("lacp-doctor"), "--json"]
        if with_hints:
            args.append("--fix-hints")
        return await self._run(*args)

    async def doctor_fix(self) -> dict:
        return await self._run(self._bin("lacp-doctor"), "--fix", "--json")

    async def run_shell(self, command: str) -> dict:
        """Run an arbitrary shell command and return output."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.root,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
        except asyncio.TimeoutError:
            return {"ok": False, "error": "timed out after 60s"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
        }

    async def agent_id(self) -> dict:
        return await self._run(self._bin("lacp-agent-id"), "show", "--json")

    async def provenance_verify(self) -> dict:
        return await self._run(
            self._bin("lacp-provenance"), "verify", "--json"
        )

    async def runs_list(self, limit: int = 5) -> dict:
        return await self._run(
            self._bin("lacp-runs"), "list", "--limit", str(limit), "--json"
        )

    async def hooks_audit(self) -> dict:
        return await self._run(
            self._bin("lacp-claude-hooks"), "audit", "--json"
        )

    async def hooks_apply_profile(self, profile: str) -> dict:
        return await self._run(
            self._bin("lacp-claude-hooks"),
            "apply-profile",
            "--profile",
            profile,
            "--json",
        )

    async def hooks_repair(self) -> dict:
        return await self._run(
            self._bin("lacp-claude-hooks"), "repair", "--json"
        )

    async def runs_show(self, run_id: str) -> dict:
        return await self._run(
            self._bin("lacp-runs"), "show", run_id, "--json"
        )

    async def brain_doctor(self, with_hints: bool = False) -> dict:
        args = [self._bin("lacp-brain-doctor"), "--json"]
        if with_hints:
            args.append("--fix-hints")
        return await self._run(*args)

    async def memory_kpi(self) -> dict:
        return await self._run(
            self._bin("lacp-memory-kpi"), "--json"
        )

    async def brain_stack_status(self) -> dict:
        return await self._run(
            self._bin("lacp-brain-stack"), "status", "--json"
        )

    async def brain_stack_audit(self) -> dict:
        return await self._run(
            self._bin("lacp-brain-stack"), "audit", "--json"
        )

    async def brain_expand(self, apply: bool = False) -> dict:
        args = [self._bin("lacp-brain-expand"), "--json"]
        if apply:
            args.append("--apply")
        return await self._run(*args)
