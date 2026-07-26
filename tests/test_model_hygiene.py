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


def test_chat_service_refreshes_generated_litellm_catalog(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    generated: list[str] = []
    legacy_catalog = """model_list:
  - model_name: claude-3-5-sonnet
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20240620
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-3-5-haiku
    litellm_params:
      model: anthropic/claude-3-5-haiku-20241022
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: gemini-1.5-pro
    litellm_params:
      model: gemini/gemini-1.5-pro-latest
      api_key: os.environ/GEMINI_API_KEY
  - model_name: gemini-1.5-flash
    litellm_params:
      model: gemini/gemini-1.5-flash-latest
      api_key: os.environ/GEMINI_API_KEY
"""

    def run_generator(script_path: Path, home: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1" help >/dev/null; ensure_litellm_config',
                "_",
                str(script_path),
            ],
            env={**os.environ, "HOME": str(home)},
            text=True,
            capture_output=True,
            check=False,
        )

    for index, relative_path in enumerate(
        (
            "scripts/afs/chat-service.sh",
            "scripts/afs/utils/chat-service.sh",
        )
    ):
        home = tmp_path / f"home-{index}"
        config_path = home / ".config" / "afs" / "litellm.yaml"
        script_path = repo_root / relative_path

        result = run_generator(script_path, home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "created"
        catalog = config_path.read_text(encoding="utf-8")
        generated.append(catalog)
        assert config_path.stat().st_mode & 0o777 == 0o600
        assert list(config_path.parent.glob("litellm.yaml.tmp.*")) == []

        config_path.chmod(0o644)
        result = run_generator(script_path, home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "unchanged"
        assert config_path.read_text(encoding="utf-8") == catalog
        assert config_path.stat().st_mode & 0o777 == 0o600

        config_path.write_text(
            "# Generated by chat-service.sh. Changes are replaced on the next config refresh.\n"
            "model_list: [{model_name: retired-model}]\n",
            encoding="utf-8",
        )
        result = run_generator(script_path, home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "updated"
        assert config_path.read_text(encoding="utf-8") == catalog
        assert config_path.stat().st_mode & 0o777 == 0o600

        config_path.write_text(legacy_catalog, encoding="utf-8")
        result = run_generator(script_path, home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "updated"
        assert config_path.read_text(encoding="utf-8") == catalog

        custom = (
            "model_list:\n"
            "  - model_name: custom-model\n"
            "    litellm_params: {model: custom/provider-model}\n"
            "  - model_name: gemini-3-pro-preview\n"
        )
        config_path.write_text(custom, encoding="utf-8")
        config_path.chmod(0o644)
        result = run_generator(script_path, home)
        assert result.returncode == 0
        assert result.stdout.strip() == "preserved"
        assert "preserving unmanaged" in result.stderr
        assert config_path.read_text(encoding="utf-8") == custom
        assert config_path.stat().st_mode & 0o777 == 0o600
        assert list(config_path.parent.glob("litellm.yaml.tmp.*")) == []

        blocked_home = tmp_path / f"blocked-home-{index}"
        blocked_path = blocked_home / ".config" / "afs" / "litellm.yaml"
        blocked_path.mkdir(parents=True)
        result = run_generator(script_path, blocked_home)
        assert result.returncode != 0
        assert "refusing to replace non-regular LiteLLM config" in result.stderr
        assert blocked_path.is_dir()

        if os.name != "nt":
            symlink_home = tmp_path / f"symlink-home-{index}"
            symlink_path = symlink_home / ".config" / "afs" / "litellm.yaml"
            symlink_path.parent.mkdir(parents=True)
            symlink_target = symlink_home / "custom-litellm.yaml"
            symlink_target.write_text(custom, encoding="utf-8")
            symlink_path.symlink_to(symlink_target)
            result = run_generator(script_path, symlink_home)
            assert result.returncode != 0
            assert "refusing to replace non-regular LiteLLM config" in result.stderr
            assert symlink_path.is_symlink()
            assert symlink_target.read_text(encoding="utf-8") == custom

    assert generated[0] == generated[1]
    catalog = generated[0]
    for model_id in (
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
        "gemini/gemini-3.1-pro-preview",
        "gemini/gemini-3.5-flash",
    ):
        assert model_id in catalog
    for retired_id in (
        "claude-3-5-sonnet",
        "claude-3-5-haiku",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-3-pro-preview",
        "openai/gpt-5.2",
        "openai/gpt-5-mini",
    ):
        assert retired_id not in catalog


def test_chat_service_enables_litellm_only_for_simple_mode(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent

    def probe(
        script_path: Path,
        *,
        mode: str,
        key_name: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(tmp_path),
            "AFS_SECRETS_FILE": "",
            "OPENAI_API_KEY": "",
            "OPENAI_API_KEYS": "",
            "OPENAI_API_BASE_URLS": "",
            "OPENROUTER_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GEMINI_API_BASE_URL": "",
            "LITELLM_MASTER_KEY": "",
            "LITELLM_API_KEY": "",
            "LITELLM_BASE_URL": "",
        }
        if key_name:
            env[key_name] = "test-only-value"
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1" help >/dev/null; load_secrets; litellm_should_run "$2"',
                "_",
                str(script_path),
                mode,
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    for index, relative_path in enumerate(
        (
            "scripts/afs/chat-service.sh",
            "scripts/afs/utils/chat-service.sh",
        )
    ):
        script_path = repo_root / relative_path
        assert probe(script_path, mode="simple", key_name="OPENAI_API_KEY").returncode != 0
        assert probe(script_path, mode="simple", key_name="GEMINI_API_KEY").returncode == 0
        assert probe(script_path, mode="full", key_name="OPENAI_API_KEY").returncode != 0
        assert probe(script_path, mode="simple").returncode != 0

        sync_home = tmp_path / f"sync-home-{index}"
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(sync_home),
            "AFS_SECRETS_FILE": "",
            "OPENAI_API_KEY": "test-only-value",
            "OPENAI_API_KEYS": "",
            "OPENAI_API_BASE_URLS": "",
            "OPENROUTER_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
            "GEMINI_API_KEY": "test-only-gemini-value",
            "LITELLM_MASTER_KEY": "",
            "LITELLM_API_KEY": "",
        }
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1" help >/dev/null; sync_openwebui_secrets 1',
                "_",
                str(script_path),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        openwebui_env = (
            sync_home / ".config" / "afs" / "openwebui.secrets.env"
        ).read_text(encoding="utf-8")
        assert "https://api.openai.com/v1" in openwebui_env
        assert "http://litellm:4000/v1" in openwebui_env

        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1" help >/dev/null; sync_litellm_secrets',
                "_",
                str(script_path),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        litellm_env = (
            sync_home / ".config" / "afs" / "litellm.env"
        ).read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=test-only-gemini-value" in litellm_env
        assert "OPENAI_API_KEY=test-only-value" in litellm_env
