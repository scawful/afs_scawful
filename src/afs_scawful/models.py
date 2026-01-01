"""Model deployment and management."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Model deployment targets
TargetType = Literal["ollama", "python", "studio"]


@dataclass
class ModelInfo:
    """Information about a trained model."""

    name: str
    path: Path
    size_gb: float
    has_lora: bool
    has_merged: bool
    has_gguf: bool
    has_ollama: bool
    checkpoints: list[str]


@dataclass
class DeploymentConfig:
    """Configuration for model deployment."""

    model_name: str
    target: TargetType
    quantization: str = "Q4_K_M"
    skip_merge: bool = False
    skip_gguf: bool = False


def get_infra_dir() -> Path:
    """Get the infra directory path."""
    # Assume we're in src/afs_scawful/models.py
    return Path(__file__).parent.parent.parent / "infra"


def get_models_dir() -> Path:
    """Get the models directory path."""
    return Path(__file__).parent.parent.parent / "models"


def list_models() -> list[ModelInfo]:
    """List all available trained models."""
    models_dir = get_models_dir()
    if not models_dir.exists():
        return []

    models = []
    for model_dir in models_dir.iterdir():
        if not model_dir.is_dir():
            continue
        if model_dir.name.startswith("."):
            continue

        # Check for LoRA adapters
        lora_path = model_dir / "lora_adapters"
        has_lora = lora_path.exists() and (lora_path / "adapter_model.safetensors").exists()

        # Check for merged model
        merged_dir = model_dir.parent / f"{model_dir.name}_merged"
        has_merged = merged_dir.exists()

        # Check for GGUF
        gguf_pattern = f"{model_dir.name}*.gguf"
        has_gguf = bool(list(model_dir.parent.glob(gguf_pattern)))

        # Check for Ollama model
        ollama_name = f"qwen-asm-{model_dir.name}"
        has_ollama = check_ollama_model_exists(ollama_name)

        # Get checkpoints
        checkpoints = sorted([d.name for d in model_dir.glob("checkpoint-*") if d.is_dir()])

        # Calculate size
        size_bytes = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
        size_gb = size_bytes / (1024**3)

        models.append(
            ModelInfo(
                name=model_dir.name,
                path=model_dir,
                size_gb=size_gb,
                has_lora=has_lora,
                has_merged=has_merged,
                has_gguf=has_gguf,
                has_ollama=has_ollama,
                checkpoints=checkpoints,
            )
        )

    return sorted(models, key=lambda m: m.name)


def get_model_info(model_name: str) -> ModelInfo | None:
    """Get information about a specific model."""
    models = list_models()
    for model in models:
        if model.name == model_name:
            return model
    return None


def check_ollama_model_exists(model_name: str) -> bool:
    """Check if an Ollama model exists."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return model_name in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False


def deploy_to_ollama(
    model_name: str,
    quantization: str = "Q4_K_M",
    skip_merge: bool = False,
    skip_gguf: bool = False,
) -> bool:
    """Deploy a model to Ollama.

    Args:
        model_name: Name of the model to deploy
        quantization: Quantization type (Q4_K_M, Q5_K_M, Q8_0, Q4_K_S)
        skip_merge: Skip LoRA merge if already done
        skip_gguf: Skip GGUF conversion if already done

    Returns:
        True if deployment succeeded, False otherwise
    """
    infra_dir = get_infra_dir()
    script_path = infra_dir / "create_ollama_model.sh"

    if not script_path.exists():
        print(f"Error: Deployment script not found at {script_path}")
        return False

    # Build environment
    env = os.environ.copy()
    if skip_merge:
        env["SKIP_MERGE"] = "1"
    if skip_gguf:
        env["SKIP_GGUF"] = "1"

    # Run deployment script
    try:
        result = subprocess.run(
            [str(script_path), model_name, quantization],
            cwd=infra_dir.parent,
            env=env,
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error deploying model: {e}")
        return False


def test_model_ollama(model_name: str) -> bool:
    """Test a model deployed to Ollama.

    Args:
        model_name: Name of the model (e.g., "7b_asm_v4")

    Returns:
        True if test succeeded, False otherwise
    """
    infra_dir = get_infra_dir()
    script_path = infra_dir / "test_ollama_model.sh"

    if not script_path.exists():
        print(f"Error: Test script not found at {script_path}")
        return False

    ollama_model_name = f"qwen-asm-{model_name}"

    # Run test script
    try:
        result = subprocess.run(
            [str(script_path), ollama_model_name],
            cwd=infra_dir.parent,
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing model: {e}")
        return False


def test_model_python(model_name: str, prompt: str) -> bool:
    """Test a model using Python CLI.

    Args:
        model_name: Name of the model
        prompt: Test prompt

    Returns:
        True if test succeeded, False otherwise
    """
    infra_dir = get_infra_dir()
    script_path = infra_dir / "test_model_cli.py"
    venv_python = infra_dir.parent / "venv_testing" / "bin" / "python3"

    if not script_path.exists():
        print(f"Error: Test script not found at {script_path}")
        return False

    if not venv_python.exists():
        print("Error: Testing environment not set up. Run:")
        print(f"  cd {infra_dir.parent}")
        print("  ./infra/setup_testing.sh")
        return False

    model_info = get_model_info(model_name)
    if not model_info or not model_info.has_lora:
        print(f"Error: Model {model_name} not found or missing LoRA adapters")
        return False

    # Determine base model from name
    if "7b" in model_name.lower():
        base_model = "Qwen/Qwen2.5-Coder-7B-Instruct"
    elif "14b" in model_name.lower():
        base_model = "Qwen/Qwen2.5-Coder-14B-Instruct"
    else:
        base_model = "Qwen/Qwen2.5-Coder-7B-Instruct"

    lora_path = model_info.path / "lora_adapters"

    # Run test
    try:
        result = subprocess.run(
            [
                str(venv_python),
                str(script_path),
                "--base",
                base_model,
                "--lora",
                str(lora_path),
                "--prompt",
                prompt,
                "--max-tokens",
                "200",
            ],
            cwd=infra_dir.parent,
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error testing model: {e}")
        return False


def chat_with_model(model_name: str) -> bool:
    """Start an interactive chat with a model.

    Args:
        model_name: Name of the model

    Returns:
        True if chat started successfully, False otherwise
    """
    ollama_model_name = f"qwen-asm-{model_name}"

    if not check_ollama_model_exists(ollama_model_name):
        print(f"Error: Ollama model '{ollama_model_name}' not found.")
        print(f"Deploy it first with: afs models deploy {model_name}")
        return False

    # Run interactive chat
    try:
        subprocess.run(["ollama", "run", ollama_model_name], check=False)
        return True
    except Exception as e:
        print(f"Error starting chat: {e}")
        return False


def backup_model(model_name: str) -> bool:
    """Backup a model to all configured locations.

    Args:
        model_name: Name of the model to backup

    Returns:
        True if backup succeeded, False otherwise
    """
    infra_dir = get_infra_dir()
    backup_script = infra_dir / "post_training.sh"
    model_info = get_model_info(model_name)

    if not model_info:
        print(f"Error: Model {model_name} not found")
        return False

    if not backup_script.exists():
        print(f"Error: Backup script not found at {backup_script}")
        return False

    # Run backup script
    try:
        result = subprocess.run(
            [str(backup_script), str(model_info.path)],
            cwd=infra_dir.parent,
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error backing up model: {e}")
        return False


def verify_backups(model_name: str) -> bool:
    """Verify model backups exist in all locations.

    Args:
        model_name: Name of the model to verify

    Returns:
        True if all backups verified, False otherwise
    """
    infra_dir = get_infra_dir()
    verify_script = infra_dir / "verify_backups.sh"

    if not verify_script.exists():
        print(f"Error: Verify script not found at {verify_script}")
        return False

    # Run verification script
    try:
        result = subprocess.run(
            [str(verify_script), model_name],
            cwd=infra_dir.parent,
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error verifying backups: {e}")
        return False


def print_model_status(model: ModelInfo) -> None:
    """Print detailed status for a model."""
    print(f"\nModel: {model.name}")
    print(f"Path: {model.path}")
    print(f"Size: {model.size_gb:.2f} GB")
    print()
    print("Status:")
    print(f"  LoRA adapters: {'✓' if model.has_lora else '✗'}")
    print(f"  Merged model:  {'✓' if model.has_merged else '✗'}")
    print(f"  GGUF file:     {'✓' if model.has_gguf else '✗'}")
    print(f"  Ollama model:  {'✓' if model.has_ollama else '✗'}")

    if model.checkpoints:
        print()
        print(f"Checkpoints: {', '.join(model.checkpoints)}")

    print()
    print("Next steps:")
    if not model.has_ollama:
        print(f"  Deploy to Ollama: afs models deploy {model.name}")
    else:
        print(f"  Chat with model: afs models chat {model.name}")
        print(f"  Test model: afs models test {model.name}")
