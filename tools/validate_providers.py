#!/usr/bin/env python3
"""Validate AFS provider endpoints and model availability.

Checks chat_registry.toml for agent providers, verifies base URLs,
optional model list endpoints, and can run a tiny chat probe.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import tomllib

REGISTRY_PATH = Path(os.path.expanduser("~/src/lab/afs-scawful/config/chat_registry.toml"))


def _env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _first_from_semicolon_list(value: str) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip()


def _openai_models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") or base.endswith("/api/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _openai_chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") or base.endswith("/api/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


@dataclass
class AgentConfig:
    name: str
    provider: str
    model_id: str
    base_url: str = ""
    api_key_env: str = ""


def load_registry() -> list[AgentConfig]:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry not found at {REGISTRY_PATH}")
    with REGISTRY_PATH.open("rb") as f:
        data = tomllib.load(f)

    agents: list[AgentConfig] = []
    for model in data.get("models", []):
        name = model.get("name")
        if not name:
            continue
        agents.append(
            AgentConfig(
                name=name,
                provider=str(model.get("provider", "studio")),
                model_id=str(model.get("model_id", "")),
                base_url=str(model.get("base_url", "")),
                api_key_env=str(model.get("api_key_env", "")),
            )
        )
    return agents


def resolve_base_url(provider: str, agent: AgentConfig) -> str:
    if agent.base_url:
        return agent.base_url

    provider = provider.lower()
    if provider == "ollama":
        return _env_first("OLLAMA_HOST", "AFS_OLLAMA_HOST") or "http://localhost:11434"
    if provider == "studio":
        return _env_first("LMSTUDIO_BASE_URL", "AFS_STUDIO_BASE_URL") or "http://localhost:1234/v1"
    if provider == "openrouter":
        return _env_first("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    if provider == "openai":
        return _env_first("OPENAI_BASE_URL", "OPENAI_API_BASE_URL") or "https://api.openai.com/v1"
    if provider in {"litellm", "anthropic", "gemini", "vertex"}:
        return _env_first("LITELLM_BASE_URL", "AFS_LITELLM_BASE_URL") or "http://localhost:4000/v1"
    return ""


def resolve_api_key(provider: str, agent: AgentConfig) -> str:
    if agent.api_key_env:
        return os.getenv(agent.api_key_env, "")
    provider = provider.lower()
    if provider == "openai":
        return _env_first("OPENAI_API_KEY")
    if provider == "openrouter":
        return _env_first("OPENROUTER_API_KEY")
    if provider in {"litellm", "anthropic", "gemini", "vertex"}:
        return _env_first("LITELLM_MASTER_KEY", "LITELLM_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
    return ""


def check_endpoint(client: httpx.Client, url: str, api_key: str | None = None) -> tuple[bool, str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = client.get(url, headers=headers, timeout=3.0)
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}"
        return True, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, exc.__class__.__name__


def probe_chat(
    client: httpx.Client,
    base_url: str,
    api_key: str | None,
    model_id: str,
) -> tuple[bool, str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0.0,
        "stream": False,
    }
    try:
        resp = client.post(
            _openai_chat_url(base_url),
            headers=headers,
            json=payload,
            timeout=8.0,
        )
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}"
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AFS provider endpoints")
    parser.add_argument("--agent", action="append", help="Specific agent(s) to check")
    parser.add_argument("--provider", action="append", help="Filter providers")
    parser.add_argument("--live", action="store_true", help="Perform a tiny chat probe per agent")
    args = parser.parse_args()

    agents = load_registry()
    if args.agent:
        agents = [a for a in agents if a.name in set(args.agent)]
    if args.provider:
        providers = {p.lower() for p in args.provider}
        agents = [a for a in agents if a.provider.lower() in providers]

    if not agents:
        print("No agents to check.")
        return 1

    print(f"Checking {len(agents)} agents...")

    with httpx.Client(timeout=6.0) as client:
        for agent in agents:
            provider = agent.provider.lower()
            base_url = resolve_base_url(provider, agent)
            api_key = resolve_api_key(provider, agent)
            key_ok = "yes" if api_key else "no"

            if provider == "ollama":
                url = f"{base_url.rstrip('/')}/api/tags"
                ok, detail = check_endpoint(client, url)
                print(f"{agent.name:<18} {provider:<10} {detail:<10} models: {agent.model_id} (key={key_ok})")
            else:
                url = _openai_models_url(base_url) if base_url else ""
                if not base_url:
                    print(f"{agent.name:<18} {provider:<10} missing-base-url models: {agent.model_id} (key={key_ok})")
                    continue
                ok, detail = check_endpoint(client, url, api_key if provider != "studio" else None)
                print(f"{agent.name:<18} {provider:<10} {detail:<10} models: {agent.model_id} (key={key_ok})")

            if args.live:
                if provider == "ollama":
                    # Skip live probes for Ollama (may require larger payload + model load)
                    continue
                if provider != "studio" and not api_key:
                    print(f"  - skip chat probe (missing API key)")
                    continue
                ok, detail = probe_chat(client, base_url, api_key if provider != "studio" else None, agent.model_id)
                print(f"  - chat probe: {detail}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
