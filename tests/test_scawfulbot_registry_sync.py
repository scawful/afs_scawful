from __future__ import annotations

import json
from pathlib import Path

import pytest

import afs_scawful.scawfulbot_registry_sync as registry_sync
from afs_scawful.scawfulbot_registry_sync import (
    CORE_ID,
    DEFAULT_SOURCE_REGISTRY_PATH,
    SOURCE_REGISTRY_RELATIVE,
    SYNC_GUARD,
    SYNC_SCRIPT_RELATIVE,
    build_scawfulbot_core_entry,
    sync_scawfulbot_core_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_REGISTRY_PATH = REPO_ROOT / "cores" / "registry.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_core(registry: dict, core_id: str) -> dict:
    for core in registry.get("cores", []):
        if core.get("id") == core_id:
            return core
    raise AssertionError(f"core {core_id!r} not found")


def _write_sync_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source_registry = {
        "id": "scawfulbot",
        "name": "scawfulbot",
        "description_long": "scawfulbot source of truth entry",
        "base_model": "scawfulbot.gguf",
        "parameters": {"temperature": 0.6},
        "status": "active",
        "tags": ["personality"],
    }
    target_registry = {
        "version": "1.0",
        "description": "test",
        "cores": [],
    }
    source_path = tmp_path / "source_registry.json"
    target_path = tmp_path / "target_registry.json"
    source_path.write_text(json.dumps(source_registry, indent=2) + "\n", encoding="utf-8")
    target_path.write_text(json.dumps(target_registry, indent=2) + "\n", encoding="utf-8")
    return source_path, target_path


def test_repository_core_entry_matches_scawfulbot_source_registry() -> None:
    missing = [
        path
        for path in (DEFAULT_SOURCE_REGISTRY_PATH, TARGET_REGISTRY_PATH)
        if not path.exists()
    ]
    if missing:
        pytest.skip(f"registry fixture unavailable: {missing}")

    source_registry = _read_json(DEFAULT_SOURCE_REGISTRY_PATH)
    target_registry = _read_json(TARGET_REGISTRY_PATH)

    expected = build_scawfulbot_core_entry(source_registry)
    actual = _find_core(target_registry, CORE_ID)

    assert actual == expected
    assert SYNC_GUARD in actual["notes"]
    assert SOURCE_REGISTRY_RELATIVE in actual["notes"]
    assert actual["generated_from"]["script"] == SYNC_SCRIPT_RELATIVE


def test_check_mode_detects_drift_without_writing(tmp_path: Path) -> None:
    source_registry = {
        "id": "scawfulbot",
        "name": "scawfulbot",
        "description_long": "scawfulbot source of truth entry",
        "base_model": "~/models/gguf/scawful/scawfulbot-qwen3-8b-v1-q4_k_m.gguf",
        "adapter_path": None,
        "status": "active",
        "version": "0.3.0",
        "tags": ["personality", "avatar"],
        "parameters": {"temperature": 0.6, "max_tokens": 1024},
        "runtime_model_id": "scawfulbot-qwen3-8b-v1-mlx",
        "model_history": [{"version": "0.3.0", "base": "Qwen3-8B", "date": "2026-04-11"}],
        "created_at": "2026-03-29",
        "updated_at": "2026-04-11",
    }
    target_registry = {
        "version": "1.0",
        "description": "test",
        "cores": [
            {
                "id": "scawfulbot",
                "name": "scawfulbot",
                "description": "stale",
                "base_model": "old.gguf",
                "adapter_path": None,
                "system_prompt_path": "prompts/scawfulbot.md",
                "training_data_path": "training/scawfulbot_training_template.jsonl",
                "eval_pack_path": "eval/scawfulbot_eval_cases.jsonl",
                "status": "draft",
                "version": "0.1.0",
                "tags": [],
                "parameters": {"temperature": 0.7},
                "notes": "stale",
                "created_at": "2026-03-29",
                "updated_at": "2026-04-01",
            }
        ],
    }

    source_path = tmp_path / "source_registry.json"
    target_path = tmp_path / "target_registry.json"
    source_path.write_text(json.dumps(source_registry, indent=2) + "\n", encoding="utf-8")
    target_path.write_text(json.dumps(target_registry, indent=2) + "\n", encoding="utf-8")

    before_check = target_path.read_text(encoding="utf-8")
    assert sync_scawfulbot_core_registry(source_path, target_path, check=True) is True
    assert target_path.read_text(encoding="utf-8") == before_check
    assert not (tmp_path / f".{target_path.name}.lock").exists()

    assert sync_scawfulbot_core_registry(source_path, target_path, check=False) is True
    actual_registry = _read_json(target_path)
    actual_entry = _find_core(actual_registry, CORE_ID)
    expected_entry = build_scawfulbot_core_entry(source_registry)
    assert actual_entry == expected_entry


def test_check_mode_works_in_read_only_directory(tmp_path: Path) -> None:
    source_path, target_path = _write_sync_fixture(tmp_path)
    tmp_path.chmod(0o555)
    try:
        assert sync_scawfulbot_core_registry(source_path, target_path, check=True) is True
    finally:
        tmp_path.chmod(0o755)

    assert not (tmp_path / f".{target_path.name}.lock").exists()


def test_primary_checkout_root_resolves_linked_worktree_gitdir(tmp_path: Path) -> None:
    primary = tmp_path / "lab" / "afs-scawful"
    common_git_dir = primary / ".git"
    worktree_git_dir = common_git_dir / "worktrees" / "gateway"
    worktree_git_dir.mkdir(parents=True)
    (worktree_git_dir / "commondir").write_text("../..\n", encoding="utf-8")

    linked = tmp_path / "worktrees" / "gateway"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {worktree_git_dir}\n", encoding="utf-8")

    assert registry_sync._primary_checkout_root(linked) == primary


def test_default_source_registry_path_honors_environment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "registry.json"
    monkeypatch.setenv("SCAWFULBOT_REGISTRY_PATH", str(override))

    assert registry_sync._default_source_registry_path() == override


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_sync_failure_preserves_original_registry_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    source_path, target_path = _write_sync_fixture(tmp_path)
    original = target_path.read_bytes()

    def fail(*_args: object) -> None:
        raise OSError(f"simulated {failure_point} failure")

    monkeypatch.setattr(registry_sync.os, failure_point, fail)

    with pytest.raises(OSError, match=f"simulated {failure_point} failure"):
        sync_scawfulbot_core_registry(source_path, target_path)

    assert target_path.read_bytes() == original
    assert list(tmp_path.glob(f".{target_path.name}.*.tmp")) == []


def test_sync_locks_target_and_fsyncs_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, target_path = _write_sync_fixture(tmp_path)
    fsynced: list[Path] = []
    monkeypatch.setattr(registry_sync, "_fsync_directory", fsynced.append)

    assert sync_scawfulbot_core_registry(source_path, target_path) is True

    lock_path = tmp_path / f".{target_path.name}.lock"
    assert lock_path.exists()
    assert lock_path.stat().st_mode & 0o777 == 0o600
    assert fsynced == [tmp_path]


def test_sync_preserves_target_mode(tmp_path: Path) -> None:
    source_path, target_path = _write_sync_fixture(tmp_path)
    target_path.chmod(0o640)

    assert sync_scawfulbot_core_registry(source_path, target_path) is True

    assert target_path.stat().st_mode & 0o777 == 0o640
