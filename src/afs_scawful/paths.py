"""AFS Scawful training path helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_training_paths


def default_training_root() -> Path:
    candidate = Path.home() / "src" / "training"
    if candidate.exists():
        return candidate
    return Path.home() / ".context" / "training"


def resolve_training_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    training_root = paths.get("training_root") or paths.get("training")
    if isinstance(training_root, Path):
        return training_root
    if isinstance(training_root, str) and training_root:
        return Path(training_root).expanduser().resolve()
    datasets = paths.get("datasets")
    if isinstance(datasets, Path):
        return datasets.parent
    if isinstance(datasets, str) and datasets:
        return Path(datasets).expanduser().resolve().parent
    return default_training_root()


def resolve_datasets_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    datasets = paths.get("datasets")
    if isinstance(datasets, Path):
        return datasets
    if isinstance(datasets, str) and datasets:
        return Path(datasets).expanduser().resolve()
    return resolve_training_root(config_path=config_path) / "datasets"


def resolve_index_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    index_root = paths.get("index_root")
    if isinstance(index_root, Path):
        return index_root
    if isinstance(index_root, str) and index_root:
        return Path(index_root).expanduser().resolve()
    return resolve_training_root(config_path=config_path) / "index"
