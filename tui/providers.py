#!/usr/bin/env python3
"""LACP Provider Abstraction — unified interface for multiple LLM providers.

Supports: Anthropic (Claude), OpenAI (GPT/o-series), Google (Gemini), Ollama (local).
Auth: API keys via env vars, OAuth tokens via env or macOS Keychain.

Usage:
    from providers import create_provider, list_providers

    provider = create_provider("anthropic", model="claude-sonnet-4-20250514")
    async for chunk in provider.stream("Hello world"):
        print(chunk, end="")
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

# Add automation scripts to path for provider_router
sys.path.insert(0, str(Path(__file__).parent.parent / "automation" / "scripts"))


@dataclass
class Message:
    role: str       # "user", "assistant", "system"
    content: str


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class StreamEvent:
    type: str           # "text", "tool_use", "done", "error"
    text: str = ""
    tool_call: ToolCall | None = None
    usage: dict[str, int] = field(default_factory=dict)


class Provider(ABC):
    """Base class for LLM providers."""

    name: str
    model: str

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a response. Yields StreamEvents."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider has valid credentials."""
        ...


class AnthropicProvider(Provider):
    """Anthropic Claude provider via official SDK."""

    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            token = read_claude_oauth()
            if not token:
                raise RuntimeError(
                    "No Anthropic credentials. Set up with: lacp auth"
                )

            # CRITICAL: Unset ANTHROPIC_API_KEY during client creation.
            # The Anthropic SDK auto-reads this env var and sends x-api-key
            # header even when auth_token is set. If the API key has no credits
            # but the OAuth token works, the API rejects with 400.
            _saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                import uuid
                self._client = anthropic.Anthropic(
                    api_key=None,
                    auth_token=token,
                    max_retries=5,
                    timeout=600.0,
                    default_headers={
                        "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,prompt-caching-scope-2026-01-05,token-efficient-tools-2026-03-28",
                        "x-app": "cli",
                        "X-Claude-Code-Session-Id": str(uuid.uuid4()),
                    },
                )
            finally:
                if _saved_key is not None:
                    os.environ["ANTHROPIC_API_KEY"] = _saved_key
        return self._client

    def is_available(self) -> bool:
        return bool(read_claude_oauth())

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        with client.messages.stream(**kwargs) as stream:
            current_tool_id = ""
            current_tool_name = ""
            tool_json_parts: list[str] = []

            for event in stream:
                if not hasattr(event, "type"):
                    continue

                if event.type == "content_block_start":
                    block = event.content_block
                    if hasattr(block, "type") and block.type == "tool_use":
                        current_tool_id = block.id
                        current_tool_name = block.name
                        tool_json_parts = []
                        yield StreamEvent(
                            type="tool_use",
                            tool_call=ToolCall(id=block.id, name=block.name, input={}),
                        )

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        yield StreamEvent(type="text", text=delta.text)
                    elif hasattr(delta, "partial_json"):
                        # Accumulate tool input JSON
                        tool_json_parts.append(delta.partial_json)

                elif event.type == "content_block_stop":
                    # If we were accumulating tool JSON, emit the complete tool call
                    if current_tool_id and tool_json_parts:
                        full_json = "".join(tool_json_parts)
                        try:
                            import json as _json
                            tool_input = _json.loads(full_json)
                        except Exception:
                            tool_input = {}
                        yield StreamEvent(
                            type="tool_use",
                            tool_call=ToolCall(id=current_tool_id, name=current_tool_name, input=tool_input),
                        )
                        current_tool_id = ""
                        current_tool_name = ""
                        tool_json_parts = []

                elif event.type == "message_stop":
                    msg = stream.get_final_message()
                    yield StreamEvent(
                        type="done",
                        usage={
                            "input_tokens": msg.usage.input_tokens,
                            "output_tokens": msg.usage.output_tokens,
                        },
                    )


class OpenAIProvider(Provider):
    """OpenAI GPT/o-series provider."""

    name = "openai"

    def __init__(self, model: str = "gpt-4.1"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            token = read_codex_oauth()
            if not token:
                raise RuntimeError(
                    "No OpenAI credentials. Codex OAuth auto-detected from ~/.codex/auth.json, "
                    "or set OPENAI_API_KEY"
                )
            self._client = openai.OpenAI(api_key=token)
        return self._client

    def is_available(self) -> bool:
        return bool(read_codex_oauth())

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        client = self._get_client()

        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "stream": True,
        }

        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamEvent(type="text", text=delta.content)
            if chunk.usage:
                yield StreamEvent(
                    type="done",
                    usage={
                        "input_tokens": chunk.usage.prompt_tokens or 0,
                        "output_tokens": chunk.usage.completion_tokens or 0,
                    },
                )


class OllamaProvider(Provider):
    """Local Ollama provider."""

    name = "ollama"

    def __init__(self, model: str = "llama3.1:8b"):
        self.model = model
        self.host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

    def is_available(self) -> bool:
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.host}/api/version", timeout=2)
            return True
        except Exception:
            return False

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        import urllib.request

        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        payload = json.dumps({
            "model": self.model,
            "messages": oai_messages,
            "stream": True,
        }).encode()

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield StreamEvent(type="text", text=content)
                    if data.get("done"):
                        yield StreamEvent(type="done")
                except json.JSONDecodeError:
                    continue


# ─── Keychain helpers ─────────────────────────────────────────────


def _read_keychain_service(service: str) -> str:
    """Read a value from macOS Keychain by service name."""
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def read_claude_oauth() -> str:
    """Read Claude Code's OAuth access token.

    Priority: OAuth sources first, API key last.
    This ensures Claude Pro subscription tokens are used over
    API keys that may have zero credits.

    Sources (in order):
    1. CLAUDE_CODE_OAUTH_TOKEN env var (explicit OAuth)
    2. ~/.lacp/credentials.json (exported OAuth — always works)
    3. macOS Keychain "Claude Code-credentials" (may fail in TUI)
    4. ANTHROPIC_API_KEY env var (last — may be no-credit key)
    """
    # 1. Explicit OAuth env var
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if token:
        return token

    # 2. Credentials file (exported OAuth — works everywhere)
    creds_file = Path.home() / ".lacp" / "credentials.json"
    if creds_file.exists():
        try:
            data = json.loads(creds_file.read_text(encoding="utf-8"))
            token = data.get("anthropic_token", "")
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Keychain (may not work in Textual TUI context)
    raw = _read_keychain_service("Claude Code-credentials")
    if raw:
        try:
            data = json.loads(raw)
            token = data.get("claudeAiOauth", {}).get("accessToken", "")
            if token:
                return token
        except json.JSONDecodeError:
            pass

    # 4. ANTHROPIC_API_KEY env var (lowest priority)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return api_key

    return ""


def read_codex_oauth() -> str:
    """Read Codex/OpenAI OAuth access token.

    Sources (in order):
    1. OPENAI_API_KEY env var
    2. ~/.codex/auth.json (contains OAuth tokens from ChatGPT login)
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        return api_key

    # Codex stores auth in ~/.codex/auth.json
    auth_file = Path.home() / ".codex" / "auth.json"
    if auth_file.exists():
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            # Direct API key
            key = data.get("OPENAI_API_KEY", "")
            if key:
                return key
            # OAuth tokens (from ChatGPT login)
            tokens = data.get("tokens", {})
            access = tokens.get("access_token", "")
            if access:
                return access
        except (json.JSONDecodeError, OSError):
            pass
    return ""


def read_hermes_key() -> str:
    """Read Hermes agent API key (typically OpenRouter).

    Sources (in order):
    1. OPENROUTER_API_KEY env var
    2. ~/.hermes/.env file
    3. ~/.hermes/config.yaml
    """
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key

    # Check .env file
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "OPENROUTER_API_KEY" and v:
                    return v
                if k == "ANTHROPIC_API_KEY" and v:
                    return v
        except OSError:
            pass
    return ""


# ─── Factory ──────────────────────────────────────────────────────


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}

# Model → provider mapping (from provider_router)
MODEL_PROVIDERS = {
    # Anthropic
    "opus": ("anthropic", "claude-opus-4-20250514"),
    "sonnet": ("anthropic", "claude-sonnet-4-20250514"),
    "haiku": ("anthropic", "claude-haiku-4-5-20251001"),
    "claude": ("anthropic", "claude-sonnet-4-20250514"),
    # OpenAI
    "o3": ("openai", "o3"),
    "o4-mini": ("openai", "o4-mini"),
    "gpt-4.1": ("openai", "gpt-4.1"),
    "gpt-5": ("openai", "gpt-5"),
    "codex": ("openai", "gpt-5.3-codex"),
    # Ollama
    "llama": ("ollama", "llama3.1:8b"),
    "qwen": ("ollama", "qwen2.5:72b"),
    "local": ("ollama", "llama3.1:8b"),
}


def create_provider(provider_name: str = "anthropic", model: str = "") -> Provider:
    """Create a provider instance. Accepts shorthand model names."""
    # Check if model is a shorthand alias
    if model in MODEL_PROVIDERS:
        resolved_provider, resolved_model = MODEL_PROVIDERS[model]
        provider_name = resolved_provider
        model = resolved_model

    cls = PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(PROVIDERS.keys())}")

    return cls(model=model) if model else cls()


def list_providers() -> list[dict[str, Any]]:
    """List all providers with availability status."""
    result = []
    for name, cls in PROVIDERS.items():
        try:
            instance = cls()
            available = instance.is_available()
        except Exception:
            available = False
        result.append({"name": name, "available": available})
    return result
