"""AFS Scawful training path helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_training_paths


def _configured_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str) and value:
        return Path(value).expanduser().resolve()
    return None


def default_training_root() -> Path:
    candidate = Path.home() / "src" / "training"
    if candidate.exists():
        return candidate
    return Path.home() / ".context" / "training"


def resolve_training_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    configured = _configured_path(paths.get("training_root") or paths.get("training"))
    if configured and configured.exists():
        return configured
    datasets = _configured_path(paths.get("datasets"))
    if datasets and datasets.parent.exists():
        return datasets.parent
    return default_training_root()


def resolve_datasets_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    configured = _configured_path(paths.get("datasets"))
    if configured and configured.exists():
        return configured
    return resolve_training_root(config_path=config_path) / "datasets"


def resolve_index_root(config_path: Path | None = None) -> Path:
    data = load_training_paths(config_path=config_path)
    paths: dict[str, Any] = data.get("paths", {}) if isinstance(data, dict) else {}
    configured = _configured_path(paths.get("index_root"))
    if configured and configured.exists():
        return configured
    return resolve_training_root(config_path=config_path) / "index"
