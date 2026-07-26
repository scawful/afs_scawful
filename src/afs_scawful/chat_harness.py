"""Interactive chat harness with provider and router support."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore

from .integrations.google_genai_client import GoogleAIStudioClient, VertexAIClient
from .integrations.ollama_client import OllamaClient
from .integrations.openai_client import OpenAIClient
from .integrations.anthropic_client import AnthropicClient


_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
ProviderType = Literal["ollama", "studio", "gemini", "vertex", "openai", "anthropic"]


@dataclass
class ChatModel:
    """Model entry for chat registry."""

    name: str
    provider: ProviderType
    model_id: str
    role: str = ""
    description: str = ""
    system_prompt: str = ""
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    canonical_name: str = ""
    visibility: str = "public"
    domain: str = ""
    mode: str = ""
    thinking_tier: str = ""
    options: dict[str, object] = field(default_factory=dict)


@dataclass
class PromptProfile:
    """Domain/mode prompt overlay profile."""

    name: str
    keywords: list[str] = field(default_factory=list)
    system_prompt: str = ""


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
    domain_profiles: dict[str, PromptProfile] = field(default_factory=dict)
    mode_profiles: dict[str, PromptProfile] = field(default_factory=dict)
    profile_defaults: dict[str, str] = field(default_factory=dict)

    def list_models(
        self,
        provider: ProviderType | None = None,
        *,
        include_hidden: bool = False,
    ) -> list[ChatModel]:
        models = list(self.models.values())
        if provider:
            models = [m for m in models if m.provider == provider]
        if not include_hidden:
            models = [m for m in models if m.visibility != "hidden"]
        return sorted(models, key=lambda m: m.name)

    def list_routers(self) -> list[ChatRouter]:
        return sorted(self.routers.values(), key=lambda r: r.name)

    def list_domain_profiles(self) -> list[PromptProfile]:
        return sorted(self.domain_profiles.values(), key=lambda profile: profile.name)

    def list_mode_profiles(self) -> list[PromptProfile]:
        return sorted(self.mode_profiles.values(), key=lambda profile: profile.name)

    def resolve_model(self, name: str, provider: ProviderType | None = None) -> ChatModel:
        if name in self.models:
            return self.models[name]
        for model in self.models.values():
            if name in model.aliases:
                return model
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

    def resolve_domain_profile(self, name: str) -> PromptProfile | None:
        return self.domain_profiles.get(name)

    def resolve_mode_profile(self, name: str) -> PromptProfile | None:
        return self.mode_profiles.get(name)

    @staticmethod
    def _infer_profile(
        profiles: dict[str, PromptProfile],
        prompt: str,
    ) -> PromptProfile | None:
        if not prompt:
            return None
        prompt_lower = prompt.lower()
        for profile in profiles.values():
            if profile.keywords and any(keyword in prompt_lower for keyword in profile.keywords):
                return profile
        return None

    def infer_domain_profile(self, prompt: str) -> PromptProfile | None:
        return self._infer_profile(self.domain_profiles, prompt)

    def infer_mode_profile(self, prompt: str) -> PromptProfile | None:
        return self._infer_profile(self.mode_profiles, prompt)

    def default_domain_profile(self) -> PromptProfile | None:
        name = self.profile_defaults.get("domain", "")
        if not name:
            return None
        return self.resolve_domain_profile(name)

    def default_mode_profile(self) -> PromptProfile | None:
        name = self.profile_defaults.get("mode", "")
        if not name:
            return None
        return self.resolve_mode_profile(name)

    def resolve_runtime_profiles(
        self,
        model: ChatModel,
        prompt: str,
        *,
        domain_override: str | None,
        mode_override: str | None,
        thinking_tier: str | None = None,
    ) -> tuple[PromptProfile | None, PromptProfile | None, str]:
        explicit_domain = str(domain_override or "").strip().lower()
        resolved_domain = (
            self.resolve_domain_profile(explicit_domain)
            if explicit_domain
            else self.infer_domain_profile(prompt)
        )
        if resolved_domain is None:
            resolved_domain = self.resolve_domain_profile(model.domain.strip().lower() or "") or self.default_domain_profile()

        explicit_mode = str(mode_override or "").strip().lower()
        resolved_mode = (
            self.resolve_mode_profile(explicit_mode)
            if explicit_mode
            else self.infer_mode_profile(prompt)
        )
        if resolved_mode is None:
            resolved_mode = self.resolve_mode_profile(model.mode.strip().lower() or "") or self.default_mode_profile()

        resolved_tier = _normalize_thinking_tier(thinking_tier)
        if not resolved_tier:
            resolved_tier = _normalize_thinking_tier(model.thinking_tier)
        return (
            resolved_domain,
            resolved_mode,
            resolved_tier,
        )

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


def _resolve_registry_relative_path(registry_path: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = registry_path.parent / candidate
    return candidate.resolve()


def _load_model_system_prompt(model: dict[str, object], registry_path: Path) -> str:
    parts: list[str] = []

    prompt_path_value = model.get("system_prompt_path")
    if isinstance(prompt_path_value, str) and prompt_path_value.strip():
        prompt_path = _resolve_registry_relative_path(registry_path, prompt_path_value)
        if not prompt_path.exists():
            model_name = model.get("name", "(unknown)")
            raise FileNotFoundError(
                f"system_prompt_path not found for model '{model_name}': {prompt_path}"
            )
        parts.append(prompt_path.read_text(encoding="utf-8"))

    inline_prompt = model.get("system_prompt")
    if isinstance(inline_prompt, str) and inline_prompt.strip():
        parts.append(inline_prompt)

    return "\n\n".join(part.strip() for part in parts if part.strip())


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
        options = model.get("options")
        if options is None:
            options = model.get("parameters", {})
        options = options or {}
        if not isinstance(options, dict):
            options = {}
        system_prompt = _load_model_system_prompt(model, path)
        registry.models[name] = ChatModel(
            name=name,
            provider=provider,
            model_id=model_id,
            role=model.get("role", "") or "",
            description=model.get("description", "") or "",
            system_prompt=system_prompt,
            tags=list(model.get("tags", []) or []),
            aliases=list(model.get("aliases", []) or []),
            canonical_name=model.get("alias_for", "") or "",
            visibility=model.get("visibility", "public") or "public",
            domain=model.get("domain", "") or "",
            mode=model.get("mode", "") or "",
            thinking_tier=model.get("thinking_tier", "") or "",
            options=options,
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

    for profile in payload.get("domain_profiles", []) or []:
        name = str(profile.get("name", "") or "").strip()
        if not name:
            continue
        keywords = [str(value).lower() for value in (profile.get("keywords", []) or []) if str(value).strip()]
        registry.domain_profiles[name] = PromptProfile(
            name=name,
            keywords=keywords,
            system_prompt=str(profile.get("system_prompt", "") or "").strip(),
        )

    for profile in payload.get("mode_profiles", []) or []:
        name = str(profile.get("name", "") or "").strip()
        if not name:
            continue
        keywords = [str(value).lower() for value in (profile.get("keywords", []) or []) if str(value).strip()]
        registry.mode_profiles[name] = PromptProfile(
            name=name,
            keywords=keywords,
            system_prompt=str(profile.get("system_prompt", "") or "").strip(),
        )

    profile_defaults = payload.get("profile_defaults") or {}
    if isinstance(profile_defaults, dict):
        default_domain = str(profile_defaults.get("domain", "") or "").strip()
        default_mode = str(profile_defaults.get("mode", "") or "").strip()
        if default_domain:
            registry.profile_defaults["domain"] = default_domain
        if default_mode:
            registry.profile_defaults["mode"] = default_mode

    return registry


def build_provider(provider: ProviderType, ollama_host: str | None = None):
    if provider == "ollama":
        base_url = (ollama_host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        return OllamaClient(base_url=base_url)
    if provider == "studio":
        return OpenAIClient(
            api_key_env="LMSTUDIO_API_KEY",
            api_key=os.environ.get("LMSTUDIO_API_KEY"),
            base_url=os.environ.get("LMSTUDIO_BASE_URL") or _LMSTUDIO_BASE_URL,
            api_mode="chat",
        )
    if provider == "gemini":
        return GoogleAIStudioClient()
    if provider == "vertex":
        return VertexAIClient()
    if provider == "openai":
        return OpenAIClient()
    if provider == "anthropic":
        return AnthropicClient()
    raise ValueError(f"Unknown provider: {provider}")


def _load_system_message(system: str | None, system_path: Path | None) -> str:
    if system_path:
        return system_path.read_text(encoding="utf-8")
    return system or ""


def _merge_system_prompts(*parts: str | None) -> str:
    merged = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(merged)


def _normalize_thinking_tier(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    if normalized in {"none", "off", "false", "0"}:
        return ""
    if normalized in {"low", "medium", "high", "max"}:
        return normalized
    return ""


def _build_profile_overlay(
    target: ChatModel,
    *,
    domain_profile: PromptProfile | None = None,
    mode_profile: PromptProfile | None = None,
) -> str:
    parts: list[str] = []

    domain = (
        domain_profile.name
        if domain_profile is not None
        else (target.domain or "")
    ).strip().lower()
    mode = (
        mode_profile.name
        if mode_profile is not None
        else (target.mode or "")
    ).strip().lower()

    if domain == "adaptive":
        parts.append(
            "Before answering, classify the task as Oracle of Secrets hacked code, vanilla ALTTP disassembly, or cross-reference work. Keep those conventions separate."
        )
    elif domain == "oos":
        parts.append(
            "Treat this as Oracle of Secrets hacked-code work. Prefer Oracle-specific systems, hooks, and project conventions unless the prompt explicitly asks for vanilla behavior."
        )
    elif domain == "alttp-vanilla":
        parts.append(
            "Treat this as vanilla ALTTP disassembly work. Preserve vanilla assumptions, and do not invent Oracle-specific hooks, systems, or hacked conventions."
        )
    elif domain == "xref":
        parts.append(
            "Treat this as vanilla-to-hacked cross-reference work. Compare the vanilla ALTTP and Oracle paths explicitly, and do not collapse them into one flow."
        )

    if mode == "adaptive":
        parts.append(
            "Choose whether the task is trace, debug, or authoring work before proceeding. Do not jump into patch writing when the task is primarily trace or debug."
        )
    elif mode == "trace":
        parts.append(
            "Prioritize reading, tracing, and explanation. Do not propose or write new code unless the user explicitly asks for authoring work."
        )
    elif mode == "debug":
        parts.append(
            "Treat this as debugging work. Gather evidence, state, traces, or breakpoints before proposing a fix."
        )
    elif mode == "author":
        parts.append(
            "Treat this as authoring work. Produce concrete patches, edits, or implementation guidance once the relevant constraints are clear."
        )

    if domain_profile and domain_profile.system_prompt.strip():
        parts.append(domain_profile.system_prompt.strip())
    if mode_profile and mode_profile.system_prompt.strip():
        parts.append(mode_profile.system_prompt.strip())

    return "\n\n".join(parts)


def _format_prompt_help() -> str:
    return (
        "Commands: /help, /exit, /bye, /reset, /model <name>, /router <name>, "
        "/domain <name|auto>, /mode <name|auto>, /profiles, /models, /routers, "
        "/tools, /tool <name> <json>\n"
        "Feedback: /good [note], /bad [note], /note <text>, /feedback stats"
    )


def _print_models(models: list[ChatModel]) -> None:
    for model in models:
        role = f" - {model.role}" if model.role else ""
        print(f"{model.name} ({model.provider}:{model.model_id}){role}")


def _print_routers(routers: list[ChatRouter]) -> None:
    for router in routers:
        print(f"{router.name} ({router.strategy}) - {router.description}")


def _print_profiles(registry: ChatRegistry) -> None:
    print("Domain profiles:")
    domain_profiles = registry.list_domain_profiles()
    if not domain_profiles:
        print("  (none)")
    for profile in domain_profiles:
        print(f"  - {profile.name}")
    print("Mode profiles:")
    mode_profiles = registry.list_mode_profiles()
    if not mode_profiles:
        print("  (none)")
    for profile in mode_profiles:
        print(f"  - {profile.name}")


def _response_label(router: ChatRouter | None, target: ChatModel) -> str:
    if router is None:
        return ""
    if router.name == "oracle":
        return "oracle"
    return target.name


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
    thinking_tier: str | None,
    domain: str | None = None,
    mode: str | None = None,
    ollama_host: str | None = None,
    registry_path: Path | None = None,
    enable_tools: bool = False,
) -> int:
    registry = load_chat_registry(registry_path)
    resolved_provider = provider or "ollama"
    providers: dict[str, Any] = {}

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

    if system_text and not router_config:
        print("System prompt enabled.")

    if not router_config and not model:
        print("Error: Provide --model or --router.")
        return 1

    active_domain = str(domain or "").strip().lower()
    if active_domain and not registry.resolve_domain_profile(active_domain):
        print(f"Error: Domain profile '{active_domain}' not found.")
        return 1

    active_mode = str(mode or "").strip().lower()
    if active_mode and not registry.resolve_mode_profile(active_mode):
        print(f"Error: Mode profile '{active_mode}' not found.")
        return 1

    tool_executor = _init_tool_executor(enable_tools)

    histories: dict[str, list[dict[str, str]]] = {}

    # Track last exchange for feedback commands
    last_user_prompt: str = ""
    last_assistant_response: str = ""
    last_model_name: str = ""

    def get_history(model_key: str) -> list[dict[str, str]]:
        if model_key not in histories:
            histories[model_key] = []
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
            if command == "/domain":
                if len(parts) < 2:
                    print(f"Current domain profile: {active_domain or 'auto'}")
                    continue
                requested_domain = parts[1].strip().lower()
                if requested_domain in {"auto", "none", "off"}:
                    active_domain = ""
                    print("Domain profile set to auto.")
                    continue
                if not registry.resolve_domain_profile(requested_domain):
                    print(f"Domain profile not found: {requested_domain}")
                    continue
                active_domain = requested_domain
                print(f"Domain profile set to {active_domain}.")
                continue
            if command == "/mode":
                if len(parts) < 2:
                    print(f"Current mode profile: {active_mode or 'auto'}")
                    continue
                requested_mode = parts[1].strip().lower()
                if requested_mode in {"auto", "none", "off"}:
                    active_mode = ""
                    print("Mode profile set to auto.")
                    continue
                if not registry.resolve_mode_profile(requested_mode):
                    print(f"Mode profile not found: {requested_mode}")
                    continue
                active_mode = requested_mode
                print(f"Mode profile set to {active_mode}.")
                continue
            if command == "/profiles":
                _print_profiles(registry)
                print(f"Current: domain={active_domain or 'auto'}, mode={active_mode or 'auto'}")
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
            if command in {"/good", "/bad", "/note"}:
                if not last_assistant_response:
                    print("No response to rate yet.")
                    continue
                from .feedback import log_feedback
                note = parts[1] if len(parts) > 1 else ""
                # /note with text → score 0 (neutral annotation)
                if command == "/good":
                    score = 1
                elif command == "/bad":
                    score = -1
                else:
                    score = 0
                log_feedback(
                    prompt=last_user_prompt,
                    response=last_assistant_response,
                    score=score,
                    model=last_model_name,
                    text=note,
                    metadata={"source": "chat_harness"},
                )
                labels = {1: "+1 good", -1: "-1 bad", 0: "noted"}
                print(f"Logged: {labels[score]}" + (f" — {note}" if note else ""))
                continue
            if command == "/feedback":
                subcommand = parts[1] if len(parts) > 1 else "stats"
                from .feedback import feedback_stats, recent_feedback
                if subcommand == "stats":
                    stats = feedback_stats()
                    print(f"Feedback ({stats['days_covered']}d): "
                          f"{stats['positive']}+ / {stats['negative']}- / "
                          f"{stats['neutral']}~ = {stats['total']} total")
                    for m, s in stats.get("by_model", {}).items():
                        print(f"  {m}: {s['positive']}+ {s['negative']}- {s['neutral']}~")
                elif subcommand == "recent":
                    for r in recent_feedback(days=3)[-10:]:
                        score_sym = "+" if r["feedback_score"] > 0 else "-" if r["feedback_score"] < 0 else "~"
                        note = f" — {r['feedback_text']}" if r.get("feedback_text") else ""
                        print(f"  [{score_sym}] {r['model']}: {r['prompt'][:60]}...{note}")
                else:
                    print("Usage: /feedback [stats|recent]")
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
            history = get_history(target.name)
            history.append({"role": "user", "content": user_input})
            resolved_domain_profile, resolved_mode_profile, resolved_thinking = registry.resolve_runtime_profiles(
                target,
                user_input,
                domain_override=active_domain,
                mode_override=active_mode,
                thinking_tier=thinking_tier,
            )
            resolved_system = _merge_system_prompts(
                target.system_prompt,
                _build_profile_overlay(
                    target,
                    domain_profile=resolved_domain_profile,
                    mode_profile=resolved_mode_profile,
                ),
                system_text,
            )

            async def chat_once():
                return await provider_client.chat(
                    model=target.model_id,
                    messages=history,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    system=resolved_system,
                    thinking_tier=resolved_thinking or None,
                    options=target.options,
                )

            response = asyncio.run(chat_once())
            if response.error:
                print(f"[{target.name}] error: {response.error}")
                continue

            history.append({"role": "assistant", "content": response.text})
            last_user_prompt = user_input
            last_assistant_response = response.text
            last_model_name = target.name
            label = _response_label(router_config, target)
            prefix = f"[{label}] " if label else ""
            print(f"{prefix}{response.text}\n")

    return 0
