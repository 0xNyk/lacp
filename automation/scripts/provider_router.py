#!/usr/bin/env python3
"""LACP Provider Router — unified multi-provider model routing.

Routes model requests to the correct agent backend using the
"provider/model" format (inspired by LiteLLM, Vercel AI Gateway, OpenRouter).

Supports:
- Unified model strings: "anthropic/opus", "openai/o3", "google/gemini-2.5-pro"
- Shorthand aliases: "opus" → "anthropic/opus", "o3" → "openai/o3"
- Fallback chains: primary provider fails → try secondary
- Cost tier classification: cheap/standard/expensive
- Difficulty-aware routing (DAAO pattern): route by task complexity

Usage:
    from provider_router import resolve_model, route_by_difficulty

    agent, model = resolve_model("opus")  # → ("claude", "opus")
    agent, model = resolve_model("openai/o3")  # → ("codex", "o3")
    agent, model = route_by_difficulty("fix a typo", available_agents)  # → cheap model

CLI:
    python3 provider_router.py resolve opus
    python3 provider_router.py resolve openai/o3
    python3 provider_router.py difficulty "implement a distributed consensus algorithm"
    python3 provider_router.py --list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelSpec:
    provider: str       # anthropic, openai, google, meta, local
    model: str          # opus, sonnet, o3, gemini-2.5-pro
    agent: str          # claude, codex, gemini, hermes, opencode
    cost_tier: str      # cheap, standard, expensive
    capabilities: list[str]  # code, reasoning, vision, fast


# Provider → agent backend mapping
PROVIDER_AGENTS = {
    "anthropic": "claude",
    "openai": "codex",
    "google": "gemini",
    "meta": "hermes",
    "local": "hermes",
}

# Known models with metadata
MODEL_REGISTRY: dict[str, ModelSpec] = {
    # Anthropic
    "anthropic/opus": ModelSpec("anthropic", "opus", "claude", "expensive", ["code", "reasoning", "vision"]),
    "anthropic/sonnet": ModelSpec("anthropic", "sonnet", "claude", "standard", ["code", "reasoning", "fast"]),
    "anthropic/haiku": ModelSpec("anthropic", "haiku", "claude", "cheap", ["fast"]),
    # OpenAI
    "openai/o3": ModelSpec("openai", "o3", "codex", "expensive", ["reasoning", "code"]),
    "openai/o4-mini": ModelSpec("openai", "o4-mini", "codex", "standard", ["reasoning", "fast"]),
    "openai/gpt-4.1": ModelSpec("openai", "gpt-4.1", "codex", "standard", ["code", "fast"]),
    # Google
    "google/gemini-2.5-pro": ModelSpec("google", "gemini-2.5-pro", "gemini", "expensive", ["code", "reasoning", "vision"]),
    "google/gemini-2.5-flash": ModelSpec("google", "gemini-2.5-flash", "gemini", "standard", ["fast", "vision"]),
    # Local/open-source (via hermes/ollama)
    "local/llama3.1:70b": ModelSpec("local", "llama3.1:70b", "hermes", "cheap", ["code"]),
    "local/qwen2.5:72b": ModelSpec("local", "qwen2.5:72b", "hermes", "cheap", ["code", "reasoning"]),
}

# Shorthand aliases (what users actually type)
ALIASES: dict[str, str] = {
    "opus": "anthropic/opus",
    "sonnet": "anthropic/sonnet",
    "haiku": "anthropic/haiku",
    "o3": "openai/o3",
    "o4-mini": "openai/o4-mini",
    "gpt-4.1": "openai/gpt-4.1",
    "gemini-2.5-pro": "google/gemini-2.5-pro",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-pro": "google/gemini-2.5-pro",
    "gemini-flash": "google/gemini-2.5-flash",
    "llama": "local/llama3.1:70b",
    "qwen": "local/qwen2.5:72b",
}

# Fallback chains: provider → fallback provider
FALLBACK_CHAINS: dict[str, list[str]] = {
    "anthropic": ["openai", "google"],
    "openai": ["anthropic", "google"],
    "google": ["anthropic", "openai"],
    "local": ["anthropic"],
}

# Cost tiers for routing
COST_TIERS = {
    "cheap": ["anthropic/haiku", "local/llama3.1:70b", "local/qwen2.5:72b"],
    "standard": ["anthropic/sonnet", "openai/gpt-4.1", "openai/o4-mini", "google/gemini-2.5-flash"],
    "expensive": ["anthropic/opus", "openai/o3", "google/gemini-2.5-pro"],
}


def resolve_model(model_str: str) -> tuple[str, str]:
    """Resolve a model string to (agent_backend, model_flag).

    Handles:
    - Full format: "anthropic/opus" → ("claude", "opus")
    - Shorthand: "opus" → ("claude", "opus")
    - Unknown: "custom-model" → ("claude", "custom-model") (passthrough)
    """
    # Check aliases first
    canonical = ALIASES.get(model_str, model_str)

    # Check registry
    if canonical in MODEL_REGISTRY:
        spec = MODEL_REGISTRY[canonical]
        return spec.agent, spec.model

    # Parse provider/model format
    if "/" in canonical:
        provider, model = canonical.split("/", 1)
        agent = PROVIDER_AGENTS.get(provider, "claude")
        return agent, model

    # Passthrough: assume current agent
    return "", model_str


def get_model_spec(model_str: str) -> ModelSpec | None:
    """Get full model spec with cost/capability metadata."""
    canonical = ALIASES.get(model_str, model_str)
    return MODEL_REGISTRY.get(canonical)


def get_fallback_models(model_str: str) -> list[tuple[str, str]]:
    """Get fallback (agent, model) pairs for a given model."""
    spec = get_model_spec(model_str)
    if not spec:
        return []

    fallbacks = []
    for fb_provider in FALLBACK_CHAINS.get(spec.provider, []):
        # Find a model from fallback provider in same cost tier
        for full_name, fb_spec in MODEL_REGISTRY.items():
            if fb_spec.provider == fb_provider and fb_spec.cost_tier == spec.cost_tier:
                fallbacks.append((fb_spec.agent, fb_spec.model))
                break
    return fallbacks


# ─── Difficulty-Aware Routing (DAAO pattern) ──────────────────────


# Complexity signals
COMPLEX_PATTERNS = [
    re.compile(r"architect|design|refactor|migrate|rewrite", re.I),
    re.compile(r"distributed|consensus|concurrent|parallel", re.I),
    re.compile(r"security|vulnerability|audit|penetration", re.I),
    re.compile(r"optimize|benchmark|profil|performance", re.I),
    re.compile(r"debug.*production|incident|outage|postmortem", re.I),
    re.compile(r"implement.*from scratch|build.*system|create.*framework", re.I),
]

SIMPLE_PATTERNS = [
    re.compile(r"fix.*typo|rename|format|lint|style", re.I),
    re.compile(r"update.*version|bump|upgrade.*dep", re.I),
    re.compile(r"add.*comment|document|readme", re.I),
    re.compile(r"simple|quick|minor|small|trivial", re.I),
    re.compile(r"list.*files|show.*status|check.*health", re.I),
]


def estimate_difficulty(task_description: str) -> str:
    """Estimate task difficulty from description. Returns: simple, moderate, complex."""
    if not task_description:
        return "moderate"

    complex_hits = sum(1 for p in COMPLEX_PATTERNS if p.search(task_description))
    simple_hits = sum(1 for p in SIMPLE_PATTERNS if p.search(task_description))

    # Length heuristic: longer descriptions tend to be more complex
    word_count = len(task_description.split())
    if word_count > 50:
        complex_hits += 1

    if complex_hits >= 2:
        return "complex"
    if simple_hits >= 2 or (simple_hits >= 1 and complex_hits == 0):
        return "simple"
    return "moderate"


def route_by_difficulty(
    task_description: str,
    available_models: list[str] | None = None,
) -> tuple[str, str]:
    """Route to appropriate model based on task difficulty (DAAO pattern).

    - Simple tasks → cheap model (haiku, gpt-4.1)
    - Moderate tasks → standard model (sonnet, o4-mini)
    - Complex tasks → expensive model (opus, o3)
    """
    difficulty = estimate_difficulty(task_description)

    tier_map = {
        "simple": "cheap",
        "moderate": "standard",
        "complex": "expensive",
    }
    target_tier = tier_map[difficulty]

    # Find best available model in target tier
    candidates = COST_TIERS.get(target_tier, COST_TIERS["standard"])

    if available_models:
        # Filter to available
        for c in candidates:
            canonical = ALIASES.get(c, c)
            if canonical in available_models or c.split("/")[-1] in available_models:
                return resolve_model(c)

    # Default to first candidate in tier
    if candidates:
        return resolve_model(candidates[0])

    return resolve_model("sonnet")


def _self_test() -> None:
    # Resolve tests
    assert resolve_model("opus") == ("claude", "opus")
    assert resolve_model("sonnet") == ("claude", "sonnet")
    assert resolve_model("o3") == ("codex", "o3")
    assert resolve_model("gemini-2.5-pro") == ("gemini", "gemini-2.5-pro")
    assert resolve_model("anthropic/opus") == ("claude", "opus")
    assert resolve_model("openai/o3") == ("codex", "o3")
    assert resolve_model("unknown-model")[1] == "unknown-model"

    # Spec tests
    spec = get_model_spec("opus")
    assert spec is not None
    assert spec.cost_tier == "expensive"
    assert "reasoning" in spec.capabilities

    # Fallback tests
    fallbacks = get_fallback_models("opus")
    assert len(fallbacks) >= 1
    assert fallbacks[0][0] != "claude"  # fallback should be different provider

    # Difficulty tests
    assert estimate_difficulty("fix a typo in README") == "simple"
    assert estimate_difficulty("architect a distributed consensus system with fault tolerance") == "complex"
    assert estimate_difficulty("add a new API endpoint") == "moderate"

    # Route by difficulty
    agent, model = route_by_difficulty("fix typo")
    assert model in ("haiku", "llama3.1:70b", "qwen2.5:72b")

    agent, model = route_by_difficulty("architect distributed system from scratch with security audit")
    assert model in ("opus", "o3", "gemini-2.5-pro")


def main() -> int:
    parser = argparse.ArgumentParser(description="LACP Provider Router")
    parser.add_argument("command", nargs="?", choices=["resolve", "difficulty", "spec"], default="")
    parser.add_argument("arg", nargs="?", default="")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if args.list:
        print("Available models:")
        for alias, canonical in sorted(ALIASES.items()):
            spec = MODEL_REGISTRY.get(canonical)
            tier = spec.cost_tier if spec else "?"
            agent = spec.agent if spec else "?"
            print(f"  {alias:20s} → {canonical:30s} [{tier:10s}] agent={agent}")
        return 0

    if args.command == "resolve" and args.arg:
        agent, model = resolve_model(args.arg)
        fallbacks = get_fallback_models(args.arg)
        spec = get_model_spec(args.arg)
        print(json.dumps({
            "input": args.arg,
            "agent": agent,
            "model": model,
            "cost_tier": spec.cost_tier if spec else "unknown",
            "capabilities": spec.capabilities if spec else [],
            "fallbacks": [{"agent": a, "model": m} for a, m in fallbacks],
        }, indent=2))
        return 0

    if args.command == "difficulty" and args.arg:
        difficulty = estimate_difficulty(args.arg)
        agent, model = route_by_difficulty(args.arg)
        print(json.dumps({
            "task": args.arg,
            "difficulty": difficulty,
            "routed_agent": agent,
            "routed_model": model,
        }, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
