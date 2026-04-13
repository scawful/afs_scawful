from __future__ import annotations

import json
from pathlib import Path

from afs_scawful.model_ops.manifests import build_training_run_manifest, mark_manifest_completed
from afs_scawful.model_ops.trainer_manifests import build_trainer_run_manifest


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_build_training_run_manifest_keeps_generic_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "dataset"
    output_dir = tmp_path / "output"
    manifest = build_training_run_manifest(
        mode="train",
        trainer="peft",
        preset="zelda-16b",
        model="deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        output_dir=output_dir,
        data_dir=data_dir,
        hyperparameters={"epochs": 1, "learning_rate": 1e-5},
        command=["python3", "train.py"],
        inputs={"dataset_manifest": {"path": "/tmp/dataset_manifest.json"}},
        metadata={"track": "zelda_smoke"},
    )

    assert manifest["status"] == "running"
    assert manifest["trainer"] == "peft"
    assert manifest["preset"] == "zelda-16b"
    assert manifest["command"] == ["python3", "train.py"]
    assert manifest["metadata"]["track"] == "zelda_smoke"
    assert manifest["inputs"]["dataset_manifest"]["path"] == "/tmp/dataset_manifest.json"


def test_build_trainer_run_manifest_tracks_train_valid_and_extra_inputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "dataset"
    output_dir = tmp_path / "output"
    _write_jsonl(data_dir / "train.jsonl", [{"text": "a"}, {"text": "b"}])
    _write_jsonl(data_dir / "valid.jsonl", [{"text": "c"}])
    system_prompt = tmp_path / "system_prompt.md"
    system_prompt.write_text("be precise\n", encoding="utf-8")

    manifest = build_trainer_run_manifest(
        mode="train",
        trainer="unsloth",
        preset="iquest-40b",
        model="Qwen/Qwen2.5-Coder-32B-Instruct",
        output_dir=output_dir,
        data_dir=data_dir,
        hyperparameters={"epochs": 2},
        tracked_inputs={
            "system_prompt": {"path": system_prompt},
            "validator_config": {"record": {"path": "/tmp/asar.toml", "sha256": "abc123"}},
        },
    )

    assert manifest["inputs"]["train_jsonl"]["rows"] == 2
    assert manifest["inputs"]["valid_jsonl"]["rows"] == 1
    assert manifest["inputs"]["system_prompt"]["path"].endswith("system_prompt.md")
    assert manifest["inputs"]["validator_config"]["sha256"] == "abc123"

    completed = mark_manifest_completed(manifest, artifacts={"adapter": "/tmp/out/adapter"})
    assert completed["status"] == "completed"
    assert completed["artifacts"]["adapter"] == "/tmp/out/adapter"
