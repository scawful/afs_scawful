"""Interactive chat harness with provider and router support."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore

from .integrations.google_genai_client import GoogleAIStudioClient, VertexAIClient
from .integrations.ollama_client import OllamaClient


ProviderType = Literal["ollama", "studio", "vertex"]


@dataclass
class ChatModel:
    """Model entry for chat registry."""

    name: str
    provider: ProviderType
    model_id: str
    role: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class RouterRule:
    """Keyword routing rule."""

    keywords: list[str]
    model: str


@dataclass
class ChatRouter:
    """Router definition."""

    name: str
    description: str = ""
    strategy: str = "keyword"  # "keyword" or "ensemble"
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    rules: list[RouterRule] = field(default_factory=list)


@dataclass
class ChatRegistry:
    """Registry of models and routers."""

    models: dict[str, ChatModel] = field(default_factory=dict)
    routers: dict[str, ChatRouter] = field(default_factory=dict)

    def list_models(self, provider: ProviderType | None = None) -> list[ChatModel]:
        models = list(self.models.values())
        if provider:
            models = [m for m in models if m.provider == provider]
        return sorted(models, key=lambda m: m.name)

    def list_routers(self) -> list[ChatRouter]:
        return sorted(self.routers.values(), key=lambda r: r.name)

    def resolve_model(self, name: str, provider: ProviderType | None = None) -> ChatModel:
        if name in self.models:
            return self.models[name]
        for model in self.models.values():
            if model.model_id == name:
                return model
        resolved_provider = provider or "ollama"
        return ChatModel(
            name=name,
            provider=resolved_provider,
            model_id=name,
        )

    def resolve_router(self, name: str) -> ChatRouter | None:
        return self.routers.get(name)

    def route_prompt(self, router: ChatRouter, prompt: str) -> list[str]:
        prompt_lower = prompt.lower()
        if router.strategy == "ensemble":
            return list(router.models)
        for rule in router.rules:
            if any(keyword in prompt_lower for keyword in rule.keywords):
                return [rule.model]
        if router.default_model:
            return [router.default_model]
        if router.rules:
            return [router.rules[0].model]
        return []


def default_registry_path() -> Path:
    return Path(__file__).parent.parent.parent / "config" / "chat_registry.toml"


def load_chat_registry(config_path: Path | None = None) -> ChatRegistry:
    path = config_path or default_registry_path()
    if not path.exists():
        return ChatRegistry()

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    registry = ChatRegistry()

    for model in payload.get("models", []):
        name = model.get("name", "")
        provider = model.get("provider", "ollama")
        model_id = model.get("model_id", name)
        if not name or not model_id:
            continue
        registry.models[name] = ChatModel(
            name=name,
            provider=provider,
            model_id=model_id,
            role=model.get("role", "") or "",
            description=model.get("description", "") or "",
            tags=list(model.get("tags", []) or []),
        )

    for router in payload.get("routers", []):
        name = router.get("name", "")
        if not name:
            continue
        rules = []
        for rule in router.get("rules", []) or []:
            keywords = [k for k in (rule.get("keywords") or []) if k]
            model = rule.get("model", "")
            if keywords and model:
                rules.append(RouterRule(keywords=keywords, model=model))
        registry.routers[name] = ChatRouter(
            name=name,
            description=router.get("description", "") or "",
            strategy=router.get("strategy", "keyword") or "keyword",
            default_model=router.get("default_model", "") or "",
            models=list(router.get("models", []) or []),
            rules=rules,
        )

    return registry


def build_provider(provider: ProviderType, ollama_host: str | None = None):
    if provider == "ollama":
        base_url = (ollama_host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        return OllamaClient(base_url=base_url)
    if provider == "studio":
        return GoogleAIStudioClient()
    if provider == "vertex":
        return VertexAIClient()
    raise ValueError(f"Unknown provider: {provider}")


def _load_system_message(system: str | None, system_path: Path | None) -> str:
    if system_path:
        return system_path.read_text(encoding="utf-8")
    return system or ""


def _format_prompt_help() -> str:
    return (
        "Commands: /help, /exit, /bye, /reset, /model <name>, /router <name>, "
        "/models, /routers, /tools, /tool <name> <json>"
    )


def _print_models(models: list[ChatModel]) -> None:
    for model in models:
        role = f" - {model.role}" if model.role else ""
        print(f"{model.name} ({model.provider}:{model.model_id}){role}")


def _print_routers(routers: list[ChatRouter]) -> None:
    for router in routers:
        print(f"{router.name} ({router.strategy}) - {router.description}")


def _init_tool_executor(enable_tools: bool):
    if not enable_tools:
        return None

    try:
        from .zelda_eval.orchestrator.tools import ToolExecutor
        from .zelda_eval.sandbox.worktree import WorktreeManager
        from .zelda_eval.sandbox.builder import AsarBuilder
        from .zelda_eval.experts.registry import ExpertRegistry
    except Exception:
        return None

    sandbox_manager = None
    sandbox_builder = None
    try:
        sandbox_manager = WorktreeManager()
        sandbox_builder = AsarBuilder()
    except FileNotFoundError:
        sandbox_manager = None
        sandbox_builder = None

    expert_registry = ExpertRegistry()
    return ToolExecutor(
        sandbox_manager=sandbox_manager,
        sandbox_builder=sandbox_builder,
        expert_registry=expert_registry,
        mcp_client=None,
    )


def run_chat(
    model: str | None,
    router: str | None,
    provider: ProviderType | None,
    system: str | None,
    system_path: Path | None,
    temperature: float,
    top_p: float,
    max_tokens: int,
    ollama_host: str | None = None,
    registry_path: Path | None = None,
    enable_tools: bool = False,
) -> int:
    registry = load_chat_registry(registry_path)
    resolved_provider = provider or "ollama"
    providers: dict[str, object] = {}

    system_text = _load_system_message(system, system_path)

    def get_provider(name: ProviderType):
        if name not in providers:
            providers[name] = build_provider(name, ollama_host=ollama_host)
        return providers[name]

    if router:
        router_config = registry.resolve_router(router)
        if not router_config:
            print(f"Error: Router '{router}' not found.")
            return 1
        print(f"Router: {router_config.name} ({router_config.strategy})")
    else:
        router_config = None

    if system_text and resolved_provider != "ollama" and not router_config:
        print("Warning: system prompt is only applied for Ollama providers.")

    if not router_config and not model:
        print("Error: Provide --model or --router.")
        return 1

    tool_executor = _init_tool_executor(enable_tools)

    histories: dict[str, list[dict[str, str]]] = {}

    def get_history(model_key: str, provider_name: ProviderType) -> list[dict[str, str]]:
        if model_key not in histories:
            histories[model_key] = []
            if system_text and provider_name == "ollama":
                histories[model_key].append({"role": "system", "content": system_text})
        return histories[model_key]

    def resolve_target(name: str) -> ChatModel:
        return registry.resolve_model(name, provider=resolved_provider)

    print(_format_prompt_help())

    while True:
        try:
            user_input = input(">>> ").strip()
        except EOFError:
            print("\nExiting.")
            return 0
        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit"}:
            return 0

        if user_input.startswith("/"):
            parts = user_input.split(" ", 2)
            command = parts[0].lower()
            if command in {"/exit", "/bye", "/quit"}:
                return 0
            if command == "/help":
                print(_format_prompt_help())
                continue
            if command == "/reset":
                histories.clear()
                print("History cleared.")
                continue
            if command == "/model":
                if len(parts) < 2:
                    print("Usage: /model <name>")
                    continue
                model = parts[1]
                router_config = None
                print(f"Model set to {model}.")
                continue
            if command == "/router":
                if len(parts) < 2:
                    print("Usage: /router <name>")
                    continue
                router = parts[1]
                router_config = registry.resolve_router(router)
                if not router_config:
                    print(f"Router not found: {router}")
                    continue
                print(f"Router set to {router_config.name} ({router_config.strategy})")
                continue
            if command == "/models":
                _print_models(registry.list_models())
                continue
            if command == "/routers":
                _print_routers(registry.list_routers())
                continue
            if command == "/tools":
                if not tool_executor:
                    print("Tools not enabled.")
                    continue
                from .zelda_eval.orchestrator.tools import get_all_tools
                tools = get_all_tools()
                for tool in tools:
                    print(f"{tool.name} ({tool.category})")
                continue
            if command == "/tool":
                if not tool_executor:
                    print("Tools not enabled.")
                    continue
                if len(parts) < 3:
                    print("Usage: /tool <name> <json-args>")
                    continue
                tool_name = parts[1]
                try:
                    args = json.loads(parts[2])
                except json.JSONDecodeError as exc:
                    print(f"Invalid JSON: {exc}")
                    continue
                result = asyncio.run(tool_executor.execute(tool_name, args))
                print(json.dumps(result, indent=2, sort_keys=True))
                continue
            print("Unknown command. Use /help.")
            continue

        if router_config:
            model_names = registry.route_prompt(router_config, user_input)
            if not model_names:
                print("Router did not return a model.")
                continue
        else:
            model_names = [model] if model else []

        for model_name in model_names:
            target = resolve_target(model_name)
            provider_client = get_provider(target.provider)
            history = get_history(target.name, target.provider)
            history.append({"role": "user", "content": user_input})

            async def chat_once():
                return await provider_client.chat(
                    model=target.model_id,
                    messages=history,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )

            response = asyncio.run(chat_once())
            if response.error:
                print(f"[{target.name}] error: {response.error}")
                continue

            history.append({"role": "assistant", "content": response.text})
            prefix = f"[{target.name}] " if router_config else ""
            print(f"{prefix}{response.text}\n")

    return 0
