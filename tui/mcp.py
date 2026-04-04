"""LACP MCP Client — connect to MCP servers for extended tool access.

Loads MCP server configs from ~/.claude/settings.local.json and
~/.claude/settings.json, launches stdio-based MCP servers, and
exposes their tools to the REPL.

MCP protocol: JSON-RPC over stdio (stdin/stdout).
Reference: https://modelcontextprotocol.io/

Usage:
    from mcp import MCPManager

    mgr = MCPManager()
    mgr.start_servers()         # launch configured servers
    tools = mgr.get_tools()     # Anthropic-format tool definitions
    result = mgr.call_tool("memory", "search_nodes", {"query": "LACP"})
    mgr.stop_all()
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MCPServer:
    name: str
    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    process: subprocess.Popen | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    request_id: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def next_id(self) -> int:
        with self._lock:
            self.request_id += 1
            return self.request_id


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self) -> None:
        self.servers: dict[str, MCPServer] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load MCP server configs from Claude settings files."""
        for settings_file in [
            Path.home() / ".claude" / "settings.local.json",
            Path.home() / ".claude" / "settings.json",
        ]:
            if not settings_file.exists():
                continue
            try:
                data = json.loads(settings_file.read_text())
                servers = data.get("mcpServers", {})
                for name, config in servers.items():
                    if name in self.servers:
                        continue  # local overrides global
                    command = config.get("command", "")
                    if not command:
                        # Skip HTTP-based servers (type: "http")
                        continue
                    self.servers[name] = MCPServer(
                        name=name,
                        command=command,
                        args=[str(a) for a in config.get("args", [])],
                        env=config.get("env", {}),
                    )
            except (json.JSONDecodeError, OSError):
                continue

    def start_server(self, name: str) -> bool:
        """Start a single MCP server. Returns True if successful."""
        server = self.servers.get(name)
        if not server:
            return False
        if server.process and server.process.poll() is None:
            return True  # already running

        env = {**os.environ, **server.env}
        # Expand ~ in env values
        for k, v in env.items():
            if isinstance(v, str) and v.startswith("~"):
                env[k] = str(Path(v).expanduser())

        try:
            cmd = [server.command] + server.args
            server.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
            # Initialize: send initialize request
            response = self._send_request(server, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lacp", "version": "0.8.0"},
            })
            if response and not response.get("error"):
                # Send initialized notification
                self._send_notification(server, "notifications/initialized", {})
                # List tools
                tools_response = self._send_request(server, "tools/list", {})
                if tools_response and "result" in tools_response:
                    server.tools = tools_response["result"].get("tools", [])
                return True
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            server.process = None
        return False

    def start_servers(self, names: list[str] | None = None) -> dict[str, bool]:
        """Start MCP servers. Returns {name: success}."""
        targets = names or list(self.servers.keys())
        results = {}
        for name in targets:
            results[name] = self.start_server(name)
        return results

    def stop_server(self, name: str) -> None:
        server = self.servers.get(name)
        if server and server.process:
            try:
                server.process.terminate()
                server.process.wait(timeout=5)
            except Exception:
                try:
                    server.process.kill()
                except Exception:
                    pass
            server.process = None

    def stop_all(self) -> None:
        for name in list(self.servers.keys()):
            self.stop_server(name)

    def get_tools(self) -> list[dict[str, Any]]:
        """Get all MCP tools in Anthropic format."""
        all_tools = []
        for server in self.servers.values():
            if not server.process or server.process.poll() is not None:
                continue
            for tool in server.tools:
                all_tools.append({
                    "name": f"mcp_{server.name}_{tool['name']}",
                    "description": f"[MCP:{server.name}] {tool.get('description', '')}",
                    "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                })
        return all_tools

    def call_tool(self, full_name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool. full_name format: mcp_{server}_{tool}"""
        # Parse server and tool name from full_name
        parts = full_name.split("_", 2)
        if len(parts) < 3 or parts[0] != "mcp":
            return json.dumps({"error": f"Invalid MCP tool name: {full_name}"})

        server_name = parts[1]
        tool_name = "_".join(parts[2:])  # handle tools with underscores

        server = self.servers.get(server_name)
        if not server or not server.process or server.process.poll() is not None:
            return json.dumps({"error": f"MCP server '{server_name}' not running"})

        response = self._send_request(server, "tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if response and "result" in response:
            result = response["result"]
            # Extract text content from MCP response
            content = result.get("content", [])
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                return "\n".join(texts) if texts else json.dumps(result)
            return json.dumps(result)
        elif response and "error" in response:
            return json.dumps({"error": response["error"]})
        return json.dumps({"error": "No response from MCP server"})

    def _send_request(self, server: MCPServer, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC request and wait for response."""
        if not server.process or not server.process.stdin or not server.process.stdout:
            return None

        req_id = server.next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        try:
            line = json.dumps(request) + "\n"
            server.process.stdin.write(line)
            server.process.stdin.flush()

            # Read response (with timeout)
            response_line = ""
            start = time.time()
            while time.time() - start < 10:  # 10s timeout
                response_line = server.process.stdout.readline()
                if response_line:
                    try:
                        resp = json.loads(response_line)
                        if resp.get("id") == req_id:
                            return resp
                        # Skip notifications
                        if "method" in resp and "id" not in resp:
                            continue
                    except json.JSONDecodeError:
                        continue
            return None
        except (BrokenPipeError, OSError):
            return None

    def _send_notification(self, server: MCPServer, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not server.process or not server.process.stdin:
            return
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            server.process.stdin.write(json.dumps(notification) + "\n")
            server.process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def status(self) -> dict[str, Any]:
        """Get status of all servers."""
        result = {}
        for name, server in self.servers.items():
            running = server.process is not None and server.process.poll() is None
            result[name] = {
                "running": running,
                "tools": len(server.tools) if running else 0,
                "command": f"{server.command} {' '.join(server.args[:2])}",
            }
        return result
