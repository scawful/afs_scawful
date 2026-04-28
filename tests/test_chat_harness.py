from __future__ import annotations

from pathlib import Path

from afs_scawful.chat_harness import ChatModel, ChatRouter, OpenAIClient, _response_label, build_provider, load_chat_registry

def test_build_provider_studio_uses_openai_compatible_lmstudio(monkeypatch) -> None:
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)

    client = build_provider("studio")

    assert isinstance(client, OpenAIClient)
    assert client.base_url == "http://127.0.0.1:1234/v1"
    assert client.api_key_env == "LMSTUDIO_API_KEY"
    assert client.send_authorization is False
    assert "Authorization" not in client._headers()


def test_load_chat_registry_supports_parameters_alias_and_system_prompt(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "tester"
provider = "studio"
model_id = "gguf/example.gguf"
system_prompt = "You are the test model."
parameters = { temperature = 0.25, top_p = 0.9 }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    registry = load_chat_registry(registry_path)
    model = registry.models["tester"]

    assert model.system_prompt == "You are the test model."
    assert model.options == {"temperature": 0.25, "top_p": 0.9}


def test_load_chat_registry_supports_system_prompt_path(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "tester.md").write_text("Loaded from disk.", encoding="utf-8")

    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "tester"
provider = "studio"
model_id = "gguf/example.gguf"
system_prompt_path = "prompts/tester.md"
system_prompt = "Inline tail."
""".strip()
        + "\n",
        encoding="utf-8",
    )

    registry = load_chat_registry(registry_path)
    model = registry.models["tester"]

    assert model.system_prompt == "Loaded from disk.\n\nInline tail."


def test_load_chat_registry_supports_domain_and_mode_profiles(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "oracle"
provider = "studio"
model_id = "gguf/zelda/oracle.gguf"
domain = "adaptive"
mode = "adaptive"

[profile_defaults]
domain = "oos"
mode = "author"

[[domain_profiles]]
name = "oos"
keywords = ["oracle", "hook"]
system_prompt = "oos overlay"

[[mode_profiles]]
name = "author"
keywords = ["patch", "implement"]
system_prompt = "author overlay"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    registry = load_chat_registry(registry_path)

    default_domain = registry.default_domain_profile()
    default_mode = registry.default_mode_profile()

    assert default_domain is not None
    assert default_domain.name == "oos"
    assert default_mode is not None
    assert default_mode.name == "author"
    inferred_domain = registry.infer_domain_profile("please inspect this oracle hook")
    inferred_mode = registry.infer_mode_profile("implement a patch")
    assert inferred_domain is not None and inferred_domain.name == "oos"
    assert inferred_mode is not None and inferred_mode.name == "author"


def test_registry_hides_legacy_oracle_aliases_from_default_model_list(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "oracle"
provider = "studio"
model_id = "gguf/oracle.gguf"
aliases = ["oracle-main-plan"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    chat_registry = load_chat_registry(registry_path)

    public_names = [model.name for model in chat_registry.list_models()]
    all_names = [model.name for model in chat_registry.list_models(include_hidden=True)]
    canonical_oracle = chat_registry.models["oracle"]

    assert "oracle" in public_names
    assert "oracle-main-plan" not in public_names
    assert "oracle-main-plan" not in all_names
    assert "oracle" in all_names
    assert "oracle-main-plan" in canonical_oracle.aliases


def test_resolve_runtime_profiles_use_model_defaults_and_explicit_overrides(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "oracle"
provider = "studio"
model_id = "gguf/oracle.gguf"
domain = "oos"
mode = "author"
thinking_tier = "medium"

[[domain_profiles]]
name = "adaptive"
keywords = ["adaptive"]
system_prompt = "adaptive domain"

[[domain_profiles]]
name = "oos"
keywords = ["oracle"]
system_prompt = "oos domain"

[[domain_profiles]]
name = "alttp-vanilla"
keywords = ["vanilla"]
system_prompt = "alttp domain"

[[mode_profiles]]
name = "author"
keywords = ["implement", "patch", "edit"]
system_prompt = "author mode"

[[mode_profiles]]
name = "trace"
keywords = ["read", "trace", "inspect"]
system_prompt = "trace mode"

[profile_defaults]
domain = "adaptive"
mode = "trace"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    registry = load_chat_registry(registry_path)
    target = registry.models["oracle"]

    domain, mode, effort = registry.resolve_runtime_profiles(
        target,
        "what is this project about?",
        domain_override="",
        mode_override="",
        thinking_tier=None,
    )
    assert domain is not None
    assert domain.name == "oos"
    assert mode is not None
    assert mode.name == "author"
    assert effort == "medium"

    domain, mode, effort = registry.resolve_runtime_profiles(
        target,
        "this seems like vanilla",
        domain_override="alttp-vanilla",
        mode_override="trace",
        thinking_tier="high",
    )
    assert domain is not None
    assert domain.name == "alttp-vanilla"
    assert mode is not None
    assert mode.name == "trace"
    assert effort == "high"

    domain, mode, effort = registry.resolve_runtime_profiles(
        target,
        "read and trace this oracle routine",
        domain_override="",
        mode_override="",
        thinking_tier=None,
    )
    assert domain is not None
    assert domain.name == "oos"
    assert mode is not None
    assert mode.name == "trace"
    assert effort == "medium"


def test_load_chat_registry_supports_visibility_alias_for_domain_and_mode(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "oracle"
provider = "studio"
model_id = "gguf/oracle.gguf"
visibility = "public"
domain = "adaptive"
mode = "adaptive"
aliases = ["oracle-main"]
thinking_tier = "medium"

[[models]]
name = "oracle-main-plan"
provider = "studio"
model_id = "gguf/oracle.gguf"
alias_for = "oracle"
visibility = "hidden"
domain = "adaptive"
mode = "adaptive"
thinking_tier = "high"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    registry = load_chat_registry(registry_path)

    assert [model.name for model in registry.list_models()] == ["oracle"]
    assert {model.name for model in registry.list_models(include_hidden=True)} == {"oracle", "oracle-main-plan"}

    canonical = registry.resolve_model("oracle-main")
    legacy = registry.resolve_model("oracle-main-plan")

    assert canonical.name == "oracle"
    assert canonical.aliases == ["oracle-main"]
    assert canonical.domain == "adaptive"
    assert canonical.mode == "adaptive"
    assert legacy.canonical_name == "oracle"
    assert legacy.visibility == "hidden"
    assert legacy.thinking_tier == "high"


def test_registry_defaults_oracle_profiles_to_adaptive_and_routes_xref_to_oracle(tmp_path: Path) -> None:
    registry_path = tmp_path / "chat_registry.toml"
    registry_path.write_text(
        """
[[models]]
name = "oracle"
provider = "studio"
model_id = "gguf/oracle.gguf"

[profile_defaults]
domain = "adaptive"
mode = "adaptive"

[[domain_profiles]]
name = "adaptive"
keywords = ["cross-reference", "vanilla"]
system_prompt = "adaptive domain"

[[mode_profiles]]
name = "adaptive"
keywords = ["hook", "patch", "trace"]
system_prompt = "adaptive mode"

[[routers]]
name = "oracle"
default_model = "oracle"

[[routers.rules]]
keywords = ["cross-reference", "vanilla"]
model = "oracle"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    chat_registry = load_chat_registry(registry_path)

    default_domain = chat_registry.default_domain_profile()
    default_mode = chat_registry.default_mode_profile()

    assert default_domain is not None
    assert default_domain.name == "adaptive"
    assert default_mode is not None
    assert default_mode.name == "adaptive"

    oracle_router = chat_registry.resolve_router("oracle")
    assert oracle_router is not None
    assert oracle_router.default_model == "oracle"
    assert chat_registry.route_prompt(oracle_router, "cross-reference this vanilla ALTTP hook point") == ["oracle"]


def test_oracle_router_response_label_hides_internal_target_name() -> None:
    router = ChatRouter(name="oracle")
    target = ChatModel(name="nayru", provider="studio", model_id="gguf/example.gguf")

    assert _response_label(router, target) == "oracle"
    assert _response_label(ChatRouter(name="avatar"), target) == "nayru"
    assert _response_label(None, target) == ""
