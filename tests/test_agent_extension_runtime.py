from __future__ import annotations

from afs_scawful.agent_model_presets import build_preset
from afs_scawful.agent_tools import create_triforce_tools


def test_agent_model_presets_export_domain_configs() -> None:
    config = build_preset("majora_lmstudio")
    assert config.model_id.endswith(".gguf")


def test_agent_model_presets_oracle_legacy_aliases_share_oracle_contract() -> None:
    canonical = build_preset("oracle_lmstudio")
    legacy_aliases = (
        "oracle_main_plan_lmstudio",
        "oracle_main_act_lmstudio",
        "switchhook_plan_lmstudio",
        "switchhook_act_lmstudio",
    )

    for alias in legacy_aliases:
        preset = build_preset(alias)
        assert preset.provider == canonical.provider
        assert preset.model_id == canonical.model_id
        assert "Oracle" in preset.system_prompt


def test_agent_tools_register_extension_bundle() -> None:
    tools = create_triforce_tools()
    names = {tool.name for tool in tools}

    assert "read_context" in names
    assert "assemble" in names
    assert "yaze_debug" in names
    assert "alttp_lookup" in names
