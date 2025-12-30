from __future__ import annotations

from pathlib import Path

from afs_scawful.config import load_training_paths, load_training_resources


def test_load_training_paths_expands_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "training_paths.toml"
    config_path.write_text(
        "[paths]\n"
        "training_root = \"~/training\"\n"
        "datasets = \"~/training/datasets\"\n",
        encoding="utf-8",
    )

    data = load_training_paths(config_path=config_path)
    paths = data["paths"]
    assert paths["training_root"] == (Path.home() / "training").resolve()
    assert paths["datasets"] == (Path.home() / "training" / "datasets").resolve()


def test_load_training_resources_expands_roots(tmp_path: Path) -> None:
    config_path = tmp_path / "training_resources.toml"
    config_path.write_text(
        "[resource_discovery]\n"
        f"resource_roots = [\"{tmp_path}\"]\n",
        encoding="utf-8",
    )

    data = load_training_resources(config_path=config_path)
    roots = data["resource_discovery"]["resource_roots"]
    assert roots == [tmp_path.resolve()]
