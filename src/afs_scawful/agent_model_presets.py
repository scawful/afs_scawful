"""Domain-specific model presets for afs-scawful."""

from __future__ import annotations

from afs.agent.models import ModelConfig, ModelProvider


def _oracle_legacy_lmstudio_preset(
    *,
    temperature: float,
    system_prompt: str,
    model_id: str = "switchhook-27b-v1",
) -> ModelConfig:
    return ModelConfig(
        provider=ModelProvider.LMSTUDIO,
        model_id=model_id,
        temperature=temperature,
        system_prompt=system_prompt,
    )


def build_preset(name: str) -> ModelConfig:
    key = name.strip().lower()
    base_oracle_prompt = (
        "You are Oracle, the mainline Zelda ROM hacking specialist. "
        "Handle Oracle of Secrets, vanilla ALTTP disassembly, and cross-reference work without mixing their conventions. "
        "Prefer canonical tool surfaces, reason from evidence, and do not invent symbols or addresses."
    )
    oracle_plan_prompt = (
        "You are Oracle-Main in planning mode. Use evidence-first reasoning for Zelda ASM, Oracle patching, and tool selection. "
        "Prefer canonical tool surfaces and do not invent symbols or addresses."
    )
    oracle_act_prompt = (
        "You are Oracle-Main in action mode. Emit only the concrete tool call, patch, or concise next step. "
        "Prefer canonical tool surfaces and do not guess."
    )
    presets = {
        "din": ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_id="din-v3-fewshot:latest",
            temperature=0.3,
            system_prompt="You are Din, a 65816 assembly optimization expert. Output only optimized code.",
        ),
        "nayru": ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_id="nayru-v5:latest",
            temperature=0.5,
            system_prompt="You are Nayru, a 65816 assembly code generation expert. Write complete, working code.",
        ),
        "farore": ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_id="farore-v1:latest",
            temperature=0.3,
            system_prompt="You are Farore, a 65816 assembly debugging expert. Find and fix bugs.",
        ),
        "veran": ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_id="veran-v1:latest",
            temperature=0.2,
            system_prompt="You are Veran, a SNES hardware expert. Provide accurate technical information.",
        ),
        "din_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/zelda/din-7b-v4-q4km.gguf",
            temperature=0.3,
            system_prompt="You are Din, a 65816 assembly optimization expert. Output only optimized code.",
        ),
        "farore_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/zelda/farore-7b-v5-q8.gguf",
            temperature=0.3,
            system_prompt="You are Farore, a 65816 assembly debugging expert. Find and fix bugs.",
        ),
        "veran_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/zelda/veran-7b-v4-q8.gguf",
            temperature=0.2,
            system_prompt="You are Veran, a SNES hardware expert. Provide accurate technical information.",
        ),
        "majora_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/zelda/majora-7b-v2-q8.gguf",
            temperature=0.4,
            system_prompt="You are Majora, an expert on the Oracle of Secrets ROM hack codebase. You have deep knowledge of its Time System, Mask System, Menu, and custom sprites.",
        ),
        "oracle_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/zelda/switchhook-27b-v1-q4km.gguf",
            temperature=0.15,
            system_prompt=base_oracle_prompt,
        ),
        "oracle_main_plan_lmstudio": _oracle_legacy_lmstudio_preset(
            temperature=0.2,
            system_prompt=oracle_plan_prompt,
            model_id="gguf/zelda/switchhook-27b-v1-q4km.gguf",
        ),
        "oracle_main_act_lmstudio": _oracle_legacy_lmstudio_preset(
            temperature=0.1,
            system_prompt=oracle_act_prompt,
            model_id="gguf/zelda/switchhook-27b-v1-q4km.gguf",
        ),
        "switchhook_plan_lmstudio": _oracle_legacy_lmstudio_preset(
            temperature=0.2,
            system_prompt=f"{oracle_plan_prompt} This preset is kept as a legacy Switchhook alias.",
            model_id="gguf/zelda/switchhook-27b-v1-q4km.gguf",
        ),
        "switchhook_act_lmstudio": _oracle_legacy_lmstudio_preset(
            temperature=0.1,
            system_prompt=f"{oracle_act_prompt} This preset is kept as a legacy Switchhook alias.",
            model_id="gguf/zelda/switchhook-27b-v1-q4km.gguf",
        ),
    }
    if key not in presets:
        raise KeyError(key)
    return presets[key]
