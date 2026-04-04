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

    # Default to Haiku — Sonnet/Opus rate limits are shared with Claude Code CLI.
    # When Claude Code is active, Sonnet/Opus OAuth quota is consumed.
    # Users can switch to Opus with /model opus when Claude Code isn't running.
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model
        self._client = None

    def _get_client(self, force_refresh: bool = False):
        if self._client is not None and not force_refresh:
            return self._client

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
                max_retries=2,
                timeout=60.0,
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

    def refresh_token(self) -> bool:
        """Force re-read of OAuth token from keychain (may have been refreshed by Claude Code)."""
        self._client = None
        try:
            self._get_client(force_refresh=True)
            return True
        except Exception:
            return False

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
    """OpenAI GPT/o-series provider.

    Supports two auth modes:
    1. OPENAI_API_KEY (sk-...) → direct SDK calls
    2. ChatGPT OAuth (~/.codex/auth.json) → delegates to codex CLI
    """

    name = "openai"

    def __init__(self, model: str = "gpt-4.1"):
        self.model = model
        self._client = None
        self._use_codex_cli = False

    def _get_client(self):
        if self._client is None:
            import openai

            # Prefer direct API key
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key and api_key.startswith("sk-"):
                self._client = openai.OpenAI(api_key=api_key)
                return self._client

            # ChatGPT OAuth tokens can't be used with the standard SDK
            # (they require model.request scope which is ChatGPT-internal).
            # Delegate to codex CLI instead.
            token = read_codex_oauth()
            if token and not token.startswith("sk-"):
                self._use_codex_cli = True
                return None

            if token:
                self._client = openai.OpenAI(api_key=token)
                return self._client

            raise RuntimeError(
                "No OpenAI credentials. Set OPENAI_API_KEY or login with: codex login"
            )
        return self._client

    def is_available(self) -> bool:
        import shutil
        # Available if we have an API key or codex CLI is installed
        if os.environ.get("OPENAI_API_KEY", ""):
            return True
        if read_codex_oauth():
            return bool(shutil.which("codex"))
        return False

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self._get_client()

        # ChatGPT OAuth → delegate to codex CLI
        if self._use_codex_cli:
            # Get the last user message
            last_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    content = m.get("content", "")
                    if isinstance(content, str):
                        last_msg = content
                    break

            if not last_msg:
                yield StreamEvent(type="text", text="No message to send.")
                yield StreamEvent(type="done")
                return

            import subprocess as _sp
            try:
                result = _sp.run(
                    ["codex", "exec", "-m", self.model, last_msg],
                    capture_output=True, text=True, timeout=120,
                    env={**os.environ, "LACP_BYPASS": "1"},
                )
                output = result.stdout.strip()
                if output:
                    yield StreamEvent(type="text", text=output)
                if result.stderr and not output:
                    yield StreamEvent(type="text", text=f"Codex error: {result.stderr[:500]}")
                yield StreamEvent(type="done")
            except _sp.TimeoutExpired:
                yield StreamEvent(type="text", text="Codex timed out after 120s")
                yield StreamEvent(type="done")
            except Exception as e:
                yield StreamEvent(type="error", text=str(e))
            return

        # Direct SDK mode (sk- API key)
        client = self._client
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
                        # Ollama returns token counts in the final message
                        usage = {}
                        if "prompt_eval_count" in data:
                            usage["input_tokens"] = data.get("prompt_eval_count", 0)
                        if "eval_count" in data:
                            usage["output_tokens"] = data.get("eval_count", 0)
                        yield StreamEvent(type="done", usage=usage if usage else {})
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
    1. CLAUDE_CODE_OAUTH_TOKEN env var
    2. macOS Keychain (freshest — Claude Code auto-refreshes here)
    3. ~/.lacp/credentials.json (fallback when keychain fails)
    4. ANTHROPIC_API_KEY env var (lowest priority)
    """
    # 1. Explicit OAuth env var
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if token:
        return token

    # 2. Keychain FIRST — Claude Code refreshes tokens here automatically
    creds_file = Path.home() / ".lacp" / "credentials.json"
    raw = _read_keychain_service("Claude Code-credentials")
    if raw:
        try:
            data = json.loads(raw)
            token = data.get("claudeAiOauth", {}).get("accessToken", "")
            if token:
                # Auto-update credentials.json with fresh token
                try:
                    creds_file.parent.mkdir(parents=True, exist_ok=True)
                    creds_file.write_text(json.dumps({
                        "anthropic_token": token,
                        "source": "keychain-auto-refresh",
                    }, indent=2))
                except OSError:
                    pass
                return token
        except json.JSONDecodeError:
            pass

    # 3. Credentials file fallback (when keychain is inaccessible)
    if creds_file.exists():
        try:
            data = json.loads(creds_file.read_text(encoding="utf-8"))
            token = data.get("anthropic_token", "")
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    # API key fallback removed — OAuth only.
    # ANTHROPIC_API_KEY env var causes conflicts (zero-credit key + OAuth token).
    # Use: lacp auth setup (exports OAuth from keychain)
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


class HermesProvider(Provider):
    """Hermes agent provider — delegates to hermes CLI."""

    name = "hermes"

    def __init__(self, model: str = "gpt-5.4"):
        self.model = model

    def is_available(self) -> bool:
        import shutil
        return bool(shutil.which("hermes"))

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run hermes in quiet mode and yield the response."""
        # Get the last user message
        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    last_msg = content
                break

        if not last_msg:
            yield StreamEvent(type="text", text="No message to send.")
            yield StreamEvent(type="done")
            return

        import subprocess as _sp
        try:
            result = _sp.run(
                ["hermes", "chat", "-Q", "-q", last_msg, "-m", self.model],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "LACP_BYPASS": "1"},
            )
            output = result.stdout.strip()
            if output:
                yield StreamEvent(type="text", text=output)
            if result.stderr and not output:
                yield StreamEvent(type="text", text=f"Hermes error: {result.stderr[:500]}")
            yield StreamEvent(type="done")
        except _sp.TimeoutExpired:
            yield StreamEvent(type="text", text="Hermes timed out after 120s")
            yield StreamEvent(type="done")
        except Exception as e:
            yield StreamEvent(type="error", text=str(e))


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "hermes": HermesProvider,
}

# Model → provider mapping (from provider_router)
MODEL_PROVIDERS = {
    # Anthropic
    "opus": ("anthropic", "claude-opus-4-6"),
    "sonnet": ("anthropic", "claude-sonnet-4-6"),
    "haiku": ("anthropic", "claude-haiku-4-5-20251001"),
    "claude": ("anthropic", "claude-sonnet-4-6"),
    # OpenAI
    "o3": ("openai", "o3"),
    "o4-mini": ("openai", "o4-mini"),
    "gpt-4.1": ("openai", "gpt-4.1"),
    "gpt-5": ("openai", "gpt-5"),
    "codex": ("openai", "gpt-5.3-codex"),
    # Hermes (uses its own routing)
    "hermes": ("hermes", "gpt-5.4"),
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
