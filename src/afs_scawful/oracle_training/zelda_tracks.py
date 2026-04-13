"""Reusable Zelda/oracle training track definitions."""

from __future__ import annotations

from copy import deepcopy

from ..model_ops.tracks import validate_track_spec

QWEN35_THINKER_BASE_MODEL = "Qwen/Qwen3.5-9B"

ORACLE_QWEN35_THINKER_PERSONAS = {
    "din_qwen35_thinker_v1": {
        "persona": "din",
        "role": "Optimization, refactoring, and cycle-level ASM tightening.",
    },
    "nayru_qwen35_thinker_v1": {
        "persona": "nayru",
        "role": "Explanation, documentation, grounded teaching, and hardware walkthroughs.",
    },
    "farore_qwen35_thinker_v1": {
        "persona": "farore",
        "role": "Autocomplete, debugging, quick patches, and FIM-oriented completions.",
    },
    "veran_qwen35_thinker_v1": {
        "persona": "veran",
        "role": "Deep context analysis, subsystem tracing, and edge-case reasoning.",
    },
    "majora_qwen35_thinker_v1": {
        "persona": "majora",
        "role": "Architecture mapping, subsystem interactions, and system-level bug triage.",
    },
    "hylia_qwen35_thinker_v1": {
        "persona": "hylia",
        "role": "Oracle of Secrets history, lore, and design-rationale recall.",
    },
    "agahnim_qwen35_thinker_v1": {
        "persona": "agahnim",
        "role": "Patch authoring, hook scaffolds, build integration, and asar workflows.",
        "chat_registry_models": [],
    },
    "sahasrahla_qwen35_thinker_v1": {
        "persona": "sahasrahla",
        "role": "ALTTP history, legacy hack provenance, Nintendo references, and historian recall.",
        "chat_registry_models": [],
    },
    "oracle_tools_qwen35_thinker_v1": {
        "persona": "oracle-tools",
        "role": "Tool-calling, emulator workflows, and structured action planning.",
    },
}


def _single_phase_train_track(
    *,
    description: str,
    bundle_name: str,
    model_name: str,
    remote_root: str,
    artifact_path: str,
    log_path: str,
    pid_path: str,
    process_pattern: str,
    downloads: dict[str, str],
    preferred_instance_name: str | None = None,
    metadata: dict | None = None,
) -> dict:
    spec = {
        "description": description,
        "bundle_name": bundle_name,
        "model_name": model_name,
        "remote_root": remote_root,
        "phase_order": ["train"],
        "phases": {
            "train": {
                "title": "Train",
                "pid": pid_path,
                "log": log_path,
                "artifact_path": artifact_path,
                "process_pattern": process_pattern,
            }
        },
        "downloads": downloads,
    }
    if preferred_instance_name:
        spec["preferred_instance_name"] = preferred_instance_name
    if metadata:
        spec["metadata"] = metadata
    return validate_track_spec(spec)


def _oracle_qwen35_thinker_track(
    track_name: str,
    *,
    persona: str,
    role: str,
    chat_registry_models: list[str] | None = None,
) -> dict:
    release_name = f"{persona}-qwen35-thinker-v1"
    dataset_dir = f"oracle_qwen35_thinkers/{persona}"
    return _single_phase_train_track(
        description=f"{persona.title()} retrain lane on Qwen 3.5 thinker with Zelda/oracle data.",
        bundle_name=track_name,
        model_name=QWEN35_THINKER_BASE_MODEL,
        remote_root="/opt/training",
        artifact_path=f"models/{release_name}/final",
        log_path=f"logs/{release_name}.log",
        pid_path=f"logs/{release_name}.pid",
        process_pattern="train_oracle_qwen35_thinker.py",
        downloads={
            "adapter_final": f"models/{release_name}/final",
        },
        metadata={
            "family": "oracle",
            "persona": persona,
            "role": role,
            "dataset_dir": dataset_dir,
            "eval_pack": "iquest_zelda_golden_v1",
            "registry_model_name": release_name,
            "chat_registry_models": list(chat_registry_models if chat_registry_models is not None else [persona]),
            "thinking_tier": "high",
            "notes": [
                "Bundle expects per-persona datasets under ~/src/training/datasets/oracle_qwen35_thinkers/<persona>/.",
                "Uses the repo-owned train_oracle_qwen35_thinker.py wrapper for remote launches.",
            ],
        },
    )


ZELDA_TRACK_SPECS = {
    "switchhook_27b_v1": _single_phase_train_track(
        description="Switchhook 27B hybrid ASM + tool LoRA training on Vast.",
        bundle_name="switchhook_27b_v1",
        model_name="Qwen/Qwen3.5-27B",
        remote_root="/workspace/training",
        artifact_path="output/switchhook-27b-v1/final",
        log_path="logs/switchhook-27b-v1.log",
        pid_path="logs/switchhook_train.pid",
        process_pattern="train_switchhook_27b_vast.py",
        downloads={
            "adapter_final": "output/switchhook-27b-v1/final",
        },
        preferred_instance_name="switchhook-27b",
        metadata={
            "family": "oracle",
            "eval_pack": "switchhook_live_smoke_v1",
            "registry_model_name": "switchhook-27b-v1",
            "chat_registry_models": ["switchhook-plan", "switchhook-act"],
            "notes": [
                "Use the Switchhook live smoke pack after training.",
                "This track assumes /workspace-style Vast nodes used by the current Zelda scripts.",
            ],
        },
    ),
    "iquest_40b_v3": _single_phase_train_track(
        description="IQuest 40B coding track using the v3 unified Zelda dataset.",
        bundle_name="iquest_40b_v3",
        model_name="IQuestLab/IQuest-Coder-V1-40B-Loop-Instruct",
        remote_root="/workspace/training",
        artifact_path="output/final",
        log_path="logs/iquest_train.log",
        pid_path="logs/iquest_train.pid",
        process_pattern="train_iquest_40b.py",
        downloads={
            "adapter_final": "output/final",
        },
        preferred_instance_name="iquest-40b",
        metadata={
            "family": "oracle",
            "eval_pack": "iquest_zelda_golden_v1",
            "registry_model_name": "iquest-40b-v3",
            "chat_registry_models": [],
        },
    ),
    "zelda_16b_v1": _single_phase_train_track(
        description="DeepSeek-Coder-V2-Lite 16B Zelda training lane.",
        bundle_name="zelda_16b_v1",
        model_name="deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        remote_root="/opt/training",
        artifact_path="models/zelda-16b-v1/final",
        log_path="logs/zelda_16b_train.log",
        pid_path="logs/zelda_16b_train.pid",
        process_pattern="train_zelda_16b_v1.py",
        downloads={
            "adapter_final": "models/zelda-16b-v1/final",
        },
        preferred_instance_name="zelda-16b",
        metadata={
            "family": "oracle",
            "dataset": "zelda_16b_mix_v1",
            "eval_pack": "iquest_zelda_golden_v1",
            "registry_model_name": "zelda-16b-v1",
            "chat_registry_models": [],
            "notes": [
                "This lane follows the draft Zelda 16B plan in docs/ZELDA_16B_TRAINING_PLAN.md.",
                "Uses the repo-owned `scripts/train_zelda_16b_v1.py` remote trainer wrapper.",
            ],
        },
    ),
}

for thinker_track_name, thinker_spec in ORACLE_QWEN35_THINKER_PERSONAS.items():
    ZELDA_TRACK_SPECS[thinker_track_name] = _oracle_qwen35_thinker_track(
        thinker_track_name,
        persona=thinker_spec["persona"],
        role=thinker_spec["role"],
        chat_registry_models=thinker_spec.get("chat_registry_models"),
    )


def list_zelda_tracks() -> list[str]:
    """Return the known Zelda/oracle training track names."""

    return sorted(ZELDA_TRACK_SPECS)


def get_zelda_track_spec(track_name: str) -> dict:
    """Return a validated Zelda/oracle training track spec."""

    try:
        spec = ZELDA_TRACK_SPECS[track_name]
    except KeyError as exc:
        raise KeyError(f"unknown Zelda track: {track_name}") from exc
    return deepcopy(spec)
