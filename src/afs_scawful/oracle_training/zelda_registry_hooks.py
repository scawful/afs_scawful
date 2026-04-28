"""Registry and artifact promotion hooks for Zelda/oracle tracks."""

from __future__ import annotations

import json
import os
import shutil
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


def default_registry_python() -> str:
    """Return the preferred python interpreter for merge and model-mgr hooks."""

    explicit = os.environ.get("ORACLE_TRAINING_PYTHON") or os.environ.get("MODEL_MGR_PYTHON")
    if explicit:
        return str(Path(explicit).expanduser())
    for name in ("python3.11", "python3"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return "python3"

def _looks_like_adapter_dir(path: Path) -> bool:
    return path.is_dir() and any(path.glob("adapter*.safetensors"))


def _registry_spec_for_track(track_name: str) -> dict[str, Any]:
    track = get_zelda_track_spec(track_name)
    metadata = track.get("metadata", {})
    model_name = metadata.get("registry_model_name")
    if not model_name:
        raise KeyError(f"unknown Zelda registry hook: {track_name}")
    return {
        "model_name": str(model_name),
        "base_model": track["model_name"],
        "chat_registry_models": [str(item) for item in metadata.get("chat_registry_models", [])],
        "track": track,
    }


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

    spec = _registry_spec_for_track(track_name)
    track = spec["track"]
    resolved_artifact = artifact_path.expanduser().resolve()
    resolved_training_root = (training_root or resolve_training_root()).expanduser().resolve()
    resolved_models_root = (training_models_root or (resolved_training_root / "models")).expanduser().resolve()
    resolved_model_mgr = (model_mgr_path or default_model_mgr_path()).expanduser().resolve()
    resolved_quantizations = quantizations or ["q4km"]
    resolved_python = default_registry_python()

    model_name = spec["model_name"]
    gguf_outdir = Path.home() / "models" / "gguf" / "zelda"
    mlx_outdir = Path.home() / "models" / "mlx" / model_name
    staged_model_dir = resolved_models_root / model_name
    model_arg = model_name
    commands: list[dict[str, Any]] = []
    env = {
        "MODELS_DIR": str(resolved_models_root),
        "MODEL_MGR_PYTHON": resolved_python,
    }

    if _looks_like_adapter_dir(resolved_artifact):
        commands.append(
            {
                "name": "merge_adapter",
                "command": [
                    resolved_python,
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
        env = {
            "MODELS_DIR": str(resolved_artifact.parent),
            "MODEL_MGR_PYTHON": resolved_python,
        }
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
