"""Domain-specific model presets for afs-scawful."""

from __future__ import annotations

from afs.agent.models import ModelConfig, ModelProvider


def build_preset(name: str) -> ModelConfig:
    key = name.strip().lower()
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
            model_id="gguf/ollama/din-7b-v4-q4km.gguf",
            temperature=0.3,
            system_prompt="You are Din, a 65816 assembly optimization expert. Output only optimized code.",
        ),
        "farore_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/ollama/farore-7b-v5-q8.gguf",
            temperature=0.3,
            system_prompt="You are Farore, a 65816 assembly debugging expert. Find and fix bugs.",
        ),
        "veran_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/ollama/veran-7b-v4-q8.gguf",
            temperature=0.2,
            system_prompt="You are Veran, a SNES hardware expert. Provide accurate technical information.",
        ),
        "majora_lmstudio": ModelConfig(
            provider=ModelProvider.LMSTUDIO,
            model_id="gguf/ollama/majora-7b-v2-q8.gguf",
            temperature=0.4,
            system_prompt="You are Majora, an expert on the Oracle of Secrets ROM hack codebase. You have deep knowledge of its Time System, Mask System, Menu, and custom sprites.",
        ),
    }
    if key not in presets:
        raise KeyError(key)
    return presets[key]
