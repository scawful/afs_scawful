from __future__ import annotations

from pathlib import Path

from afs_scawful.registry import build_dataset_registry


def test_build_dataset_registry(tmp_path: Path) -> None:
    datasets_root = tmp_path / "datasets"
    dataset_dir = datasets_root / "alpha"
    dataset_dir.mkdir(parents=True)

    (dataset_dir / "train.jsonl").write_text("{}\n", encoding="utf-8")
    (dataset_dir / "stats.json").write_text("{\"samples\": 1}\n", encoding="utf-8")
    (dataset_dir / "metadata.json").write_text("{\"source\": \"test\"}\n", encoding="utf-8")

    registry = build_dataset_registry(datasets_root)
    datasets = registry["datasets"]

    assert len(datasets) == 1
    entry = datasets[0]
    assert entry["name"] == "alpha"
    assert entry["stats"]["samples"] == 1
    assert entry["metadata"]["source"] == "test"
