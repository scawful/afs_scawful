#!/usr/bin/env python3
"""
MoE Orchestrator - Mixture of Experts routing for Oracle of Secrets.

Automatically routes prompts to the best expert based on:
1. Trained router model (if available)
2. Keyword-based classification (fallback)

Usage:
    python3 moe_orchestrator.py --prompt "Write a sprite routine"
    python3 moe_orchestrator.py --prompt "Why does this crash?" --verbose
    python3 moe_orchestrator.py --auto  # Interactive mode
"""

import argparse
import sys
import re
import os
from typing import Optional, Tuple

# Import base orchestrator helpers (registry-aware)
from orchestrator import (
    load_registry,
    resolve_base_url,
    resolve_api_key,
    call_ollama,
    call_openai_compatible,
    BACKEND_ALIASES,
)

_AGENTS_CACHE: Optional[dict] = None


def _load_agents() -> dict:
    global _AGENTS_CACHE
    if _AGENTS_CACHE is None:
        try:
            agents, _ = load_registry()
        except SystemExit as exc:
            print(f"Registry unavailable: {exc}", file=sys.stderr)
            agents = {}
        _AGENTS_CACHE = agents
    return _AGENTS_CACHE

# Remote inference configuration
REMOTE_BACKENDS = {
    "medical-mechanica": {
        "host": "http://medical-mechanica:1234",
        "description": "Windows RTX machine via Tailscale",
    },
    "vast": {
        "host": None,  # Set dynamically when spinning up instance
        "description": "vast.ai GPU instance",
    },
}

def get_lmstudio_host() -> str:
    """Get the LMStudio host, checking remote first."""
    remote = os.environ.get("LMSTUDIO_HOST")
    if remote:
        return remote
    # Check if medical-mechanica is available
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("medical-mechanica", 1234))
        sock.close()
        if result == 0:
            return "http://medical-mechanica:1234"
    except:
        pass
    return "http://localhost:1234"


def _lmstudio_base_url(remote: bool = False) -> str:
    if remote:
        override = BACKEND_ALIASES.get("lmstudio-remote")
        if override:
            return override.base_url
        return get_lmstudio_host().rstrip("/") + "/v1"
    override = BACKEND_ALIASES.get("lmstudio")
    if override:
        return override.base_url
    return "http://localhost:1234/v1"


def call_lmstudio(model: str, messages: list, base_url: str | None = None, params: dict | None = None) -> str:
    url = base_url or _lmstudio_base_url(remote=False)
    return call_openai_compatible(model, messages, base_url=url, api_key=None, params=params)


def call_lmstudio_completions(model: str, prompt: str, base_url: str | None = None, params: dict | None = None) -> str:
    messages = [{"role": "user", "content": prompt}]
    return call_lmstudio(model, messages, base_url=base_url, params=params)


def call_lmstudio_remote(model: str, messages: list) -> str:
    return call_lmstudio(model, messages, base_url=_lmstudio_base_url(remote=True))

# Expert domains and their keywords for fallback routing
EXPERT_PATTERNS = {
    "nayru": {
        "keywords": ["write", "implement", "create", "add", "code", "sprite", "routine",
                    "subroutine", "new", "make", "build", "item", "consumable", "npc"],
        "patterns": [r"Link_\w+", r"Sprite_\w+", r"\.asm$", r"implement\s+\w+"],
        "description": "Code generation (65816 ASM, sprites, items)",
    },
    "din": {
        "keywords": ["optimize", "reduce", "faster", "smaller", "cycle", "byte",
                    "performance", "space", "compress", "unroll", "bank"],
        "patterns": [r"\d+\s*bytes?", r"\d+\s*cycles?", r"too\s+(slow|large|big)"],
        "description": "Optimization (performance, size reduction)",
    },
    "farore": {
        "keywords": ["crash", "bug", "broken", "stuck", "wrong", "corrupt", "debug",
                    "trace", "fix", "issue", "error", "freeze", "loop", "infinite"],
        "patterns": [r"doesn't\s+work", r"not\s+working", r"why\s+(does|is|does)", r"stack\s+overflow"],
        "description": "Debugging (crash analysis, bug fixes)",
    },
    "veran": {
        "keywords": ["register", "ppu", "dma", "hdma", "vram", "oam", "cgram", "mode7",
                    "hardware", "spc700", "scanline", "timing", "snes"],
        "patterns": [r"\$2[0-9A-F]{3}", r"\$4[0-3][0-9A-F]{2}", r"register\s+\$"],
        "description": "Hardware (PPU, DMA, registers, timing)",
    },
    "majora": {
        "keywords": ["where", "find", "show", "how does", "existing", "codebase",
                    "pattern", "implementation", "sram", "ram", "oracle"],
        "patterns": [r"how\s+(does|is)\s+\w+\s+(work|implement)", r"find\s+the", r"\$7EF[0-9A-F]+"],
        "description": "Codebase knowledge (existing code, patterns)",
    },
    "hylia": {
        "keywords": ["dialogue", "dream", "story", "narrative", "quest", "npc",
                    "lore", "write text", "credits", "journal", "atmosphere"],
        "patterns": [r"dream\s+sequence", r"write\s+(dialogue|text|story)", r"side\s*quest"],
        "description": "Narrative (dialogue, dreams, quests, lore)",
    },
}

# Priority order for tie-breaking
EXPERT_PRIORITY = ["farore", "din", "veran", "nayru", "majora", "hylia"]


def keyword_route(prompt: str) -> Tuple[str, float]:
    """Route prompt using keyword matching. Returns (expert, confidence)."""
    prompt_lower = prompt.lower()
    scores = {}

    for expert, config in EXPERT_PATTERNS.items():
        score = 0

        # Keyword matching
        for keyword in config["keywords"]:
            if keyword in prompt_lower:
                score += 1

        # Pattern matching (stronger signal)
        for pattern in config["patterns"]:
            if re.search(pattern, prompt, re.IGNORECASE):
                score += 2

        scores[expert] = score

    # Find best match
    max_score = max(scores.values())
    if max_score == 0:
        return "majora", 0.3  # Default to codebase expert

    # Handle ties using priority
    candidates = [e for e, s in scores.items() if s == max_score]
    for expert in EXPERT_PRIORITY:
        if expert in candidates:
            confidence = min(0.9, 0.3 + (max_score * 0.15))
            return expert, confidence

    return candidates[0], 0.5


def model_route(prompt: str, router_model: str = "router-v2-q8_0.gguf") -> Tuple[str, float]:
    """Route prompt using trained router model."""
    messages = [
        {"role": "system", "content": "You are a router that classifies prompts. Respond with exactly one word: nayru, din, farore, veran, majora, or hylia."},
        {"role": "user", "content": prompt}
    ]

    try:
        result = call_lmstudio(router_model, messages)
        expert = result.strip().lower()

        if expert in EXPERT_PATTERNS:
            return expert, 0.9
        else:
            print(f"  Warning: Router returned invalid expert '{expert}', falling back to keywords")
            return keyword_route(prompt)
    except Exception as e:
        print(f"  Router model unavailable ({e}), using keyword routing")
        return keyword_route(prompt)


def route_prompt(prompt: str, use_model_router: bool = True, verbose: bool = False) -> str:
    """Route prompt to best expert."""
    if use_model_router:
        expert, confidence = model_route(prompt)
        method = "model"
    else:
        expert, confidence = keyword_route(prompt)
        method = "keyword"

    if verbose:
        print(f"\n{'='*50}")
        print(f"MoE Router Analysis")
        print(f"{'='*50}")
        print(f"Method: {method}")
        print(f"Selected: {expert} ({EXPERT_PATTERNS[expert]['description']})")
        print(f"Confidence: {confidence:.0%}")

        if method == "keyword":
            # Show scoring breakdown
            prompt_lower = prompt.lower()
            print(f"\nScoring breakdown:")
            for exp, config in EXPERT_PATTERNS.items():
                kw_hits = sum(1 for k in config["keywords"] if k in prompt_lower)
                pat_hits = sum(1 for p in config["patterns"] if re.search(p, prompt, re.I))
                if kw_hits or pat_hits:
                    print(f"  {exp}: {kw_hits} keywords, {pat_hits} patterns")
        print(f"{'='*50}\n")

    return expert


def get_agent_for_expert(expert: str, prefer_ollama: bool = False, prefer_lmstudio: bool = False) -> str:
    """Get the agent name for an expert.

    Args:
        expert: The expert name (nayru, din, farore, etc.)
        prefer_ollama: If True, prefer Ollama versions (for remote ollama)
        prefer_lmstudio: If True, prefer LMStudio versions (for remote lmstudio)
    """
    # Ollama agents (work with remote ollama on medical-mechanica)
    ollama_map = {
        "nayru": "nayru",
        "din": "din",           # din-v2:latest on ollama
        "farore": "farore",     # farore-v1:latest on ollama
        "veran": "veran",       # veran-v1:latest on ollama
        "majora": "majora",     # Would need ollama version
        "hylia": "hylia",       # Would need ollama version
    }

    # LMStudio agents (GGUF files - works local or remote)
    lmstudio_map = {
        "nayru": "nayru-lm",
        "din": "din-lm",
        "farore": "farore-lm",
        "veran": "veran-lm",
        "majora": "majora",
        "hylia": "hylia",
    }

    if prefer_ollama:
        return ollama_map.get(expert, expert)
    if prefer_lmstudio:
        return lmstudio_map.get(expert, expert)
    # Default to lmstudio for better compatibility
    return lmstudio_map.get(expert, expert)


def call_expert(expert: str, prompt: str, verbose: bool = False, remote: bool = False) -> str:
    """Call the expert agent with the prompt."""
    # For remote, prefer LMStudio agents since that's what's on medical-mechanica
    agent_name = get_agent_for_expert(expert, prefer_lmstudio=True)

    agents = _load_agents()
    if agent_name not in agents:
        print(f"Error: Agent '{agent_name}' not configured (check chat_registry.toml)")
        sys.exit(1)

    agent_config = agents[agent_name]
    model_name = agent_config["model"]
    provider = (agent_config.get("provider") or "studio").lower()

    override = None
    if remote and provider == "ollama":
        override = BACKEND_ALIASES.get("ollama-remote")
    elif remote and provider == "studio":
        override = BACKEND_ALIASES.get("lmstudio-remote")

    base_url = resolve_base_url(provider, agent_config, override)
    api_key = resolve_api_key(provider, agent_config)
    params = agent_config.get("parameters") or {}

    messages = []
    system_prompt = agent_config.get("system") or ""
    if system_prompt and "baked" not in system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    if verbose:
        print(f"Invoking {agent_name} ({model_name}) via {provider}...")

    try:
        if provider == "ollama":
            return call_ollama(model_name, messages, host=base_url)
        if provider in {"openai", "openrouter", "litellm", "anthropic", "gemini", "vertex"} and not api_key:
            return f"Missing API key for provider '{provider}'."
        return call_openai_compatible(
            model_name,
            messages,
            base_url=base_url,
            api_key=api_key if provider != "studio" else None,
            params=params,
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def interactive_mode(verbose: bool = False):
    """Run in interactive mode."""
    print("\nMoE Orchestrator - Interactive Mode")
    print("Type 'quit' to exit, 'experts' to list experts")
    print("-" * 40)

    while True:
        try:
            prompt = input("\nPrompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not prompt:
            continue
        if prompt.lower() == "quit":
            break
        if prompt.lower() == "experts":
            print("\nAvailable experts:")
            for exp, config in EXPERT_PATTERNS.items():
                print(f"  {exp:10} - {config['description']}")
            continue

        # Route and call
        expert = route_prompt(prompt, use_model_router=False, verbose=verbose)
        result = call_expert(expert, prompt, verbose=verbose)

        print(f"\n{'='*40}")
        print(f"{expert.upper()} says:")
        print("="*40)
        print(result)


def main():
    parser = argparse.ArgumentParser(
        description="MoE Orchestrator: Automatic expert routing for Oracle of Secrets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 moe_orchestrator.py --prompt "Write a pressure plate sprite"
  python3 moe_orchestrator.py --prompt "This crashes in room 0x27" --verbose
  python3 moe_orchestrator.py --prompt "Optimize this loop" --force din
  python3 moe_orchestrator.py --auto  # Interactive mode
  python3 moe_orchestrator.py --analyze "Some prompt"  # Just show routing, don't call
        """
    )
    parser.add_argument("--prompt", help="The prompt to route and execute")
    parser.add_argument("--force", choices=list(EXPERT_PATTERNS.keys()), help="Force a specific expert")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show routing details")
    parser.add_argument("--auto", action="store_true", help="Interactive mode")
    parser.add_argument("--analyze", help="Show routing analysis without calling expert")
    parser.add_argument("--no-model-router", action="store_true", help="Use keyword routing only")
    parser.add_argument("--remote", "-r", action="store_true", help="Use remote backend (medical-mechanica)")

    args = parser.parse_args()

    if args.auto:
        interactive_mode(verbose=args.verbose)
        return

    if args.analyze:
        expert = route_prompt(args.analyze, use_model_router=not args.no_model_router, verbose=True)
        print(f"\nWould route to: {expert}")
        return

    if not args.prompt:
        parser.error("--prompt required (or use --auto for interactive mode)")

    # Route the prompt
    if args.force:
        expert = args.force
        if args.verbose:
            print(f"Forcing expert: {expert}")
    else:
        expert = route_prompt(args.prompt, use_model_router=not args.no_model_router, verbose=args.verbose)

    # Call the expert
    result = call_expert(expert, args.prompt, verbose=args.verbose, remote=args.remote)

    print(f"\n{'='*40}")
    print(f"{expert.upper()} Response:")
    print("="*40)
    print(result)


if __name__ == "__main__":
    main()
