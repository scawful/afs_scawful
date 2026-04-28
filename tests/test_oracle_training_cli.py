from __future__ import annotations

from pathlib import Path

import pytest

from afs_scawful.oracle_training_cli import main


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_oracle_training_cli_validate_bundle(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    training_root = tmp_path / "training"
    datasets_root = tmp_path / "datasets"

    _write(repo_root / "docs" / "VAST_SETUP.md")
    _write(repo_root / "docs" / "MODEL_PORTFOLIO.md")
    _write(repo_root / "docs" / "eval" / "ORACLE_EVAL_MATRIX_V1_20260415.md")
    _write(repo_root / "docs" / "eval" / "oracle_boundary_effort_matrix_v1.jsonl")
    _write(repo_root / "config" / "chat_registry.toml")
    _write(training_root / "scripts" / "train_switchhook_27b_vast.py")
    _write(training_root / "scripts" / "eval_iquest_zelda.py")
    _write(training_root / "scripts" / "summarize_switchhook_live_smoke.py")
    _write(training_root / "evals" / "switchhook_live_smoke_v1.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "train.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "val.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "metadata.json", "{}\n")

    result = main(
        [
            "validate-bundle",
            "--track",
            "oracle_main_27b_v1",
            "--repo-root",
            str(repo_root),
            "--training-root",
            str(training_root),
            "--datasets-root",
            str(datasets_root),
        ]
    )

    assert result == 0


def test_oracle_training_cli_registry_plan(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    result = main(
        [
            "registry-hooks",
            "--track",
            "oracle_main_27b_v1",
            "--artifact-path",
            str(artifact),
            "--training-root",
            str(tmp_path / "training"),
            "--training-models-root",
            str(tmp_path / "models_root"),
            "--model-mgr",
            str(tmp_path / "model-mgr"),
        ]
    )

    assert result == 0


def test_oracle_training_cli_finalize_run_chains_eval_and_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[str] = []
    local_run_dir = tmp_path / "cloud_run"
    adapter_dir = local_run_dir / "adapter_final"
    adapter_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.resolve_remote_target",
        lambda **kwargs: type("Target", (), {"host": "ssh6.vast.ai", "port": 22, "remote_dir": "/workspace/training"})(),
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.unique_local_run_dir",
        lambda path: local_run_dir,
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.finalize_remote_run",
        lambda *args, **kwargs: type("Result", (), {"local_run_dir": local_run_dir, "downloaded": {"adapter_final": adapter_dir}})(),
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.build_zelda_eval_plan",
        lambda *args, **kwargs: [{"name": "eval", "command": ["python3", "eval.py"]}],
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.run_zelda_eval_hooks",
        lambda plan: seen.append("eval"),
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.build_zelda_registry_plan",
        lambda *args, **kwargs: {"commands": [{"name": "convert_q4km", "command": ["bash", "model-mgr"]}]},
    )
    monkeypatch.setattr(
        "afs_scawful.oracle_training_cli.run_zelda_registry_hooks",
        lambda plan: seen.append("registry"),
    )

    result = main(
        [
            "finalize-run",
            "--track",
            "switchhook_27b_v1",
            "--host",
            "ssh6.vast.ai",
            "--port",
            "22",
            "--run-eval-hooks",
            "--run-registry-hooks",
        ]
    )

    assert result == 0
    assert seen == ["eval", "registry"]
