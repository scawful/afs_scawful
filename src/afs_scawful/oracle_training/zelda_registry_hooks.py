"""Registry and artifact promotion hooks for Zelda/oracle tracks."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ..paths import resolve_training_root
from .zelda_tracks import get_zelda_track_spec


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture output."""

    resolved_env = os.environ.copy()
    if env:
        resolved_env.update(env)
    return subprocess.run(command, check=check, text=True, capture_output=True, env=resolved_env)


def default_model_mgr_path() -> Path:
    """Return the default model-mgr executable path."""

    return Path.home() / "src" / "tools" / "model-mgr" / "model-mgr"


REGISTRY_SPECS = {
    "switchhook_27b_v1": {
        "model_name": "switchhook-27b-v1",
        "base_model": "Qwen/Qwen3.5-27B",
        "chat_registry_models": ["switchhook-plan", "switchhook-act"],
    },
    "iquest_40b_v3": {
        "model_name": "iquest-40b-v3",
        "base_model": "IQuestLab/IQuest-Coder-V1-40B-Loop-Instruct",
        "chat_registry_models": [],
    },
    "zelda_16b_v1": {
        "model_name": "zelda-16b-v1",
        "base_model": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        "chat_registry_models": [],
    },
}


def _looks_like_adapter_dir(path: Path) -> bool:
    return path.is_dir() and any(path.glob("adapter*.safetensors"))


def build_zelda_registry_plan(
    track_name: str,
    *,
    artifact_path: Path,
    training_models_root: Path | None = None,
    training_root: Path | None = None,
    model_mgr_path: Path | None = None,
    quantizations: list[str] | None = None,
    include_mlx: bool = False,
    backup: bool = False,
) -> dict[str, Any]:
    """Build a registry/model-mgr execution plan for a finished Zelda track."""

    if track_name not in REGISTRY_SPECS:
        raise KeyError(f"unknown Zelda registry hook: {track_name}")
    spec = REGISTRY_SPECS[track_name]
    track = get_zelda_track_spec(track_name)
    resolved_artifact = artifact_path.expanduser().resolve()
    resolved_training_root = (training_root or resolve_training_root()).expanduser().resolve()
    resolved_models_root = (training_models_root or (resolved_training_root / "models")).expanduser().resolve()
    resolved_model_mgr = (model_mgr_path or default_model_mgr_path()).expanduser().resolve()
    resolved_quantizations = quantizations or ["q4km"]

    model_name = spec["model_name"]
    gguf_outdir = Path.home() / "models" / "gguf" / "zelda"
    mlx_outdir = Path.home() / "models" / "mlx" / model_name
    staged_model_dir = resolved_models_root / model_name
    model_arg = model_name
    commands: list[dict[str, Any]] = []
    env = {"MODELS_DIR": str(resolved_models_root)}

    if _looks_like_adapter_dir(resolved_artifact):
        commands.append(
            {
                "name": "merge_adapter",
                "command": [
                    "python3",
                    str(resolved_training_root / "scripts" / "merge_peft_adapter.py"),
                    "--base-model",
                    spec["base_model"],
                    "--adapter",
                    str(resolved_artifact),
                    "--output",
                    str(staged_model_dir),
                ],
            }
        )
    else:
        model_arg = resolved_artifact.name
        env = {"MODELS_DIR": str(resolved_artifact.parent)}
        staged_model_dir = resolved_artifact

    for quantize in resolved_quantizations:
        commands.append(
            {
                "name": f"convert_{quantize}",
                "command": [
                    "bash",
                    str(resolved_model_mgr),
                    "convert",
                    model_arg,
                    "--quantize",
                    quantize,
                    "--outdir",
                    str(gguf_outdir),
                ],
            }
        )

    if include_mlx:
        commands.append(
            {
                "name": "mlx_convert",
                "command": [
                    "bash",
                    str(resolved_model_mgr),
                    "mlx-convert",
                    model_name,
                    "--hf-path",
                    str(staged_model_dir),
                    "--outdir",
                    str(mlx_outdir),
                ],
            }
        )

    commands.append({"name": "artifacts_index", "command": ["bash", str(resolved_model_mgr), "artifacts-index"]})
    if backup:
        commands.append({"name": "backup", "command": ["bash", str(resolved_model_mgr), "backup", model_arg]})

    recommended_model_id = f"gguf/zelda/{model_name}-{resolved_quantizations[0]}.gguf"
    registry_updates = [
        {
            "model_name": chat_name,
            "model_id": recommended_model_id,
        }
        for chat_name in spec["chat_registry_models"]
    ]
    if not registry_updates and track.get("metadata", {}).get("eval_pack"):
        registry_updates.append(
            {
                "model_name": model_name,
                "model_id": recommended_model_id,
                "note": "create a new chat_registry.toml entry if you want this model routable locally",
            }
        )

    return {
        "track": track_name,
        "model_name": model_name,
        "artifact_path": str(resolved_artifact),
        "staged_model_dir": str(staged_model_dir),
        "environment": env,
        "commands": commands,
        "registry_updates": registry_updates,
    }


def run_zelda_registry_hooks(
    plan: dict[str, Any],
    *,
    runner=run,
) -> list[dict[str, Any]]:
    """Execute the model-mgr and merge commands from a Zelda registry plan."""

    results: list[dict[str, Any]] = []
    env = {str(key): str(value) for key, value in plan.get("environment", {}).items()}
    for item in plan.get("commands", []):
        command = list(item["command"])
        result = runner(command, env=env, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"registry hook failed: {item['name']}")
        results.append({"name": item["name"], "command": command})
    return results


def format_registry_plan(plan: dict[str, Any]) -> str:
    """Render a registry plan as formatted JSON."""

    return json.dumps(plan, indent=2)
