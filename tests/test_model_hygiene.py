from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "model_hygiene.py"
    spec = importlib.util.spec_from_file_location("model_hygiene", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prefer_canonical_path_avoids_lmstudio_aliases(tmp_path: Path) -> None:
    module = _load_module()
    canonical = tmp_path / "gguf" / "zelda" / "nayru.gguf"
    alias = tmp_path / "lmstudio" / "zelda-nayru.gguf"
    canonical.parent.mkdir(parents=True)
    alias.parent.mkdir(parents=True)
    canonical.write_bytes(b"a")
    alias.hardlink_to(canonical)

    chosen = module._prefer_canonical_path([alias, canonical])

    assert chosen == canonical


def test_annotate_groups_marks_unregistered_stale_files_for_archive(tmp_path: Path) -> None:
    module = _load_module()
    model_file = tmp_path / "gguf" / "archive" / "old.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"test")

    groups = module.scan_file_groups(tmp_path)
    annotated = module.annotate_groups(
        groups=groups,
        registry_entries=[],
        indexed_models=[],
        models_root=tmp_path,
        stale_days=30,
        now_ms=1_000_000,
    )

    assert len(annotated) == 1
    assert annotated[0].tier == "archive"
    assert "archive/" in annotated[0].reason


def test_lmstudio_deploy_script_uses_current_model_paths() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    script_path = repo_root / "scripts" / "deploy_to_lmstudio.sh"
    script = script_path.read_text(encoding="utf-8")
    registry = (repo_root / "config" / "chat_registry.toml").read_text(encoding="utf-8")

    assert "$MODELS_DIR/scawful/memory-1.5b-v1-q8.gguf" in script
    assert "$MODELS_DIR/zelda/majora-9b-q4km.gguf" in script
    assert "$MODELS_DIR/ollama/memory-v1.gguf" not in script
    assert "$MODELS_DIR/zelda/majora-7b-v2-q8.gguf" not in script
    assert 'model_id = "gguf/scawful/memory-1.5b-v1-q8.gguf"' in registry
    assert 'model_id = "gguf/zelda/majora-9b-q4km.gguf"' in registry
    assert 'model_id = "gguf/ollama/memory-v1.gguf"' not in registry
    assert 'model_id = "gguf/zelda/majora-7b-v2-q8.gguf"' not in registry


def test_lmstudio_deploy_script_relinks_stale_destinations(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    script_path = repo_root / "scripts" / "deploy_to_lmstudio.sh"
    models_dir = tmp_path / "models" / "gguf"
    lmstudio_dir = tmp_path / "lmstudio"
    output_dir = tmp_path / "output"
    mlx_dir = tmp_path / "mlx"

    current_memory = models_dir / "scawful" / "memory-1.5b-v1-q8.gguf"
    current_majora = models_dir / "zelda" / "majora-9b-q4km.gguf"
    current_memory.parent.mkdir(parents=True)
    current_majora.parent.mkdir(parents=True)
    current_memory.write_bytes(b"current-memory")
    current_majora.write_bytes(b"current-majora")

    lmstudio_dir.mkdir()
    stale_memory = tmp_path / "stale-memory.gguf"
    stale_majora = tmp_path / "stale-majora.gguf"
    stale_memory.write_bytes(b"stale-memory")
    stale_majora.write_bytes(b"stale-majora")
    (lmstudio_dir / "scawful-memory.gguf").hardlink_to(stale_memory)
    (lmstudio_dir / "zelda-majora.gguf").hardlink_to(stale_majora)

    env = os.environ.copy()
    env.update(
        {
            "MODELS_DIR": str(models_dir),
            "LMSTUDIO_MODEL_DIR": str(lmstudio_dir),
            "OUTPUT_DIR": str(output_dir),
            "MLX_DIR": str(mlx_dir),
        }
    )
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (lmstudio_dir / "scawful-memory.gguf").samefile(current_memory)
    assert (lmstudio_dir / "zelda-majora.gguf").samefile(current_majora)
    assert stale_memory.exists()
    assert stale_majora.exists()
