#!/usr/bin/env python3
"""
AFS Orchestrator (Registry Aware)
The bridge between Cloud Architects and Local Expert Models.
Dynamically loads agents from afs-scawful/config/chat_registry.toml.

Usage: python3 orchestrator.py --agent <agent_name> --prompt <task_prompt>
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import tomllib

# Paths
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


def _openai_chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") or base.endswith("/api/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


@dataclass
class BackendOverride:
    provider: str
    base_url: str


BACKEND_ALIASES = {
    "lmstudio": BackendOverride(
        provider="studio",
        base_url=_env_first("LMSTUDIO_BASE_URL", "AFS_STUDIO_BASE_URL") or "http://localhost:1234/v1",
    ),
    "lmstudio-remote": BackendOverride(
        provider="studio",
        base_url=_env_first("LMSTUDIO_REMOTE_BASE_URL") or "http://medical-mechanica:1234/v1",
    ),
    "ollama": BackendOverride(
        provider="ollama",
        base_url=_env_first("OLLAMA_HOST", "AFS_OLLAMA_HOST") or "http://localhost:11434",
    ),
    "ollama-remote": BackendOverride(
        provider="ollama",
        base_url=_env_first("OLLAMA_REMOTE_HOST") or "http://medical-mechanica:11434",
    ),
    "gateway": BackendOverride(
        provider="openai",
        base_url=_env_first("AFS_GATEWAY_URL") or "http://localhost:8000/v1",
    ),
    "litellm": BackendOverride(
        provider="litellm",
        base_url=_env_first("LITELLM_BASE_URL", "AFS_LITELLM_BASE_URL") or "http://localhost:4000/v1",
    ),
    "openai": BackendOverride(
        provider="openai",
        base_url=_env_first("OPENAI_BASE_URL", "OPENAI_API_BASE_URL")
        or _first_from_semicolon_list(_env_first("OPENAI_API_BASE_URLS"))
        or "https://api.openai.com/v1",
    ),
    "openrouter": BackendOverride(
        provider="openrouter",
        base_url=_env_first("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
    ),
}

def load_registry():
    """Parse the TOML registry to build agent + router dictionaries."""
    if not REGISTRY_PATH.exists():
        print(f"Error: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)
        
    with open(REGISTRY_PATH, "rb") as f:
        data = tomllib.load(f)
        
    agents = {}
    for model in data.get("models", []):
        name = model.get("name")
        if not name:
            continue
            
        agents[name] = {
            "model": model.get("model_id"),
            "provider": model.get("provider", "studio"),
            "system": model.get("system_prompt", ""),
            "parameters": model.get("parameters", {}),
            "base_url": model.get("base_url", ""),
            "api_key_env": model.get("api_key_env", ""),
        }
    routers = {}
    for router in data.get("routers", []):
        router_name = router.get("name")
        if not router_name:
            continue
        routers[router_name] = {
            "strategy": router.get("strategy", "keyword"),
            "default_model": router.get("default_model"),
            "rules": router.get("rules", []),
        }
    return agents, routers


def resolve_base_url(provider: str, agent_config: dict, override: BackendOverride | None = None) -> str:
    if override:
        return override.base_url
    if agent_config.get("base_url"):
        return agent_config["base_url"]

    provider = provider.lower()
    if provider == "ollama":
        return _env_first("OLLAMA_HOST", "AFS_OLLAMA_HOST") or "http://localhost:11434"
    if provider == "studio":
        return _env_first("LMSTUDIO_BASE_URL", "AFS_STUDIO_BASE_URL") or "http://localhost:1234/v1"
    if provider == "openrouter":
        return _env_first("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    if provider == "openai":
        return _env_first("OPENAI_BASE_URL", "OPENAI_API_BASE_URL") \
            or _first_from_semicolon_list(_env_first("OPENAI_API_BASE_URLS")) \
            or "https://api.openai.com/v1"
    if provider in {"litellm", "anthropic", "gemini", "vertex"}:
        return _env_first("LITELLM_BASE_URL", "AFS_LITELLM_BASE_URL") or "http://localhost:4000/v1"
    return ""


def resolve_api_key(provider: str, agent_config: dict) -> str:
    custom_env = agent_config.get("api_key_env")
    if custom_env:
        return os.getenv(custom_env, "")

    provider = provider.lower()
    if provider == "openai":
        return _env_first("OPENAI_API_KEY")
    if provider == "openrouter":
        return _env_first("OPENROUTER_API_KEY")
    if provider in {"litellm", "anthropic", "gemini", "vertex"}:
        return _env_first("LITELLM_MASTER_KEY", "LITELLM_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
    return ""


def select_router_model(router: dict, prompt: str) -> str | None:
    if not router:
        return None
    strategy = router.get("strategy", "keyword")
    if strategy != "keyword":
        return router.get("default_model")
    lowered = prompt.lower()
    for rule in router.get("rules", []):
        keywords = rule.get("keywords", [])
        if any(keyword.lower() in lowered for keyword in keywords if isinstance(keyword, str)):
            return rule.get("model")
    return router.get("default_model")

def call_ollama(model: str, messages: list, host: str | None = None) -> str:
    """Call Ollama API."""
    base_url = host or resolve_base_url("ollama", {}, None)
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]
    except Exception as e:
        return f"Error calling Ollama: {e}"

def call_openai_compatible(
    model: str,
    messages: list,
    base_url: str,
    api_key: str | None = None,
    params: dict | None = None,
) -> str:
    """Call an OpenAI-compatible chat API."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": -1,  # Unlimited for local backends
        "stream": False,
    }
    if params:
        payload.update(params)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = _openai_chat_url(base_url)
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                try:
                    err = response.json()
                    return f"Error {response.status_code}: {err.get('error', {}).get('message', 'Unknown error')}"
                except Exception:
                    return f"Error {response.status_code}: {response.text}"
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error calling OpenAI-compatible endpoint: {e}"

def main():
    agents, routers = load_registry()
    
    parser = argparse.ArgumentParser(
        description="AFS Orchestrator: Registry-driven local AI bridge."
    )
    parser.add_argument("--agent", help="The expert agent to invoke.")
    parser.add_argument("--router", help="Router name to auto-select an agent.")
    parser.add_argument("--prompt", help="The instruction/prompt for the agent.")
    parser.add_argument("--list-agents", action="store_true", help="List available agents.")
    parser.add_argument("--list-routers", action="store_true", help="List available routers.")
    parser.add_argument("--backend", help="Backend override (lmstudio, lmstudio-remote, ollama, ollama-remote, gateway, litellm, openai, openrouter).")
    parser.add_argument("--base-url", help="Override base URL for the selected provider.")
    parser.add_argument("--provider", help="Override provider (ollama/studio/openai/openrouter/litellm/anthropic/gemini).")
    
    args = parser.parse_args()

    if args.list_agents:
        print(f"{'AGENT':<20} {'PROVIDER':<10} {'MODEL ID'}")
        print("-" * 60)
        for name, config in agents.items():
            print(f"{name:<20} {config['provider']:<10} {config['model']}")
        sys.exit(0)

    if args.list_routers:
        print(f"{'ROUTER':<16} {'STRATEGY':<10} {'DEFAULT MODEL'}")
        print("-" * 60)
        for name, router in routers.items():
            print(f"{name:<16} {router.get('strategy','-'):<10} {router.get('default_model','-')}")
        sys.exit(0)

    if not args.prompt:
        parser.error("--prompt is required")

    selected_agent = args.agent
    if not selected_agent and args.router:
        router = routers.get(args.router)
        if not router:
            print(f"Error: Unknown router '{args.router}'")
            sys.exit(1)
        selected_agent = select_router_model(router, args.prompt)
        if not selected_agent:
            print(f"Error: Router '{args.router}' has no default model")
            sys.exit(1)

    if not selected_agent:
        parser.error("--agent or --router is required")

    if selected_agent not in agents:
        print(f"Error: Unknown agent '{selected_agent}'")
        sys.exit(1)

    agent_config = agents[selected_agent]
    messages = []
    
    # 1. System Prompt (Critical Fix: Always inject if present)
    if agent_config["system"]:
        messages.append({"role": "system", "content": agent_config["system"]})
        
    # 2. User Prompt
    messages.append({"role": "user", "content": args.prompt})
    
    provider = (args.provider or agent_config["provider"] or "studio").lower()
    override = BACKEND_ALIASES.get(args.backend) if args.backend else None
    if override:
        provider = override.provider

    base_url = args.base_url or resolve_base_url(provider, agent_config, override)
    api_key = resolve_api_key(provider, agent_config)

    print(f"⚡ Invoking {selected_agent} via {provider}...")
    # print(f"DEBUG: System Prompt: {agent_config['system'][:50]}...")

    if provider == "ollama":
        result = call_ollama(agent_config["model"], messages, host=base_url)
    elif provider in {"studio", "openai", "openrouter", "litellm", "anthropic", "gemini", "vertex"}:
        if provider in {"openai", "openrouter", "litellm", "anthropic", "gemini", "vertex"} and not api_key:
            result = f"Missing API key for provider '{provider}'. Set OPENAI_API_KEY/OPENROUTER_API_KEY or LITELLM_API_KEY."
        elif not base_url:
            result = f"Missing base URL for provider '{provider}'."
        else:
            result = call_openai_compatible(
                agent_config["model"],
                messages,
                base_url=base_url,
                api_key=api_key if provider != "studio" else None,
                params=agent_config["parameters"],
            )
    else:
        result = f"Unsupported provider: {provider}"
        
    print("\n" + "="*60)
    print(result)
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
