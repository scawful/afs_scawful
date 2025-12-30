"""AFS Scawful plugin config helpers."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def _expand_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _default_config_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    return [
        Path.home() / ".config" / "afs" / "afs_scawful",
        Path.home() / ".config" / "afs" / "plugins" / "afs_scawful" / "config",
        repo_root / "config",
    ]


def _find_config(filename: str) -> Path | None:
    for base in _default_config_dirs():
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


def _load_toml(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_training_paths(config_path: Path | None = None) -> dict[str, dict[str, Path]]:
    path = config_path or _find_config("training_paths.toml")
    data = _load_toml(path)
    expanded: dict[str, dict[str, Path]] = {}
    for section in ["paths", "knowledge_bases"]:
        if section in data and isinstance(data[section], dict):
            expanded[section] = {
                key: _expand_path(value)
                for key, value in data[section].items()
                if isinstance(value, str)
            }
    return expanded


def load_training_resources(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or _find_config("training_resources.toml")
    data = _load_toml(path)
    if "resource_discovery" in data and isinstance(data["resource_discovery"], dict):
        resource = data["resource_discovery"]
        if "resource_roots" in resource:
            resource["resource_roots"] = [
                _expand_path(p) for p in resource["resource_roots"] if isinstance(p, str)
            ]
    return data


def load_research_paths(config_path: Path | None = None) -> dict[str, dict[str, Path]]:
    path = config_path or _find_config("research_paths.toml")
    data = _load_toml(path)
    expanded: dict[str, dict[str, Path]] = {}
    if "paths" in data and isinstance(data["paths"], dict):
        expanded["paths"] = {
            key: _expand_path(value)
            for key, value in data["paths"].items()
            if isinstance(value, str)
        }
    return expanded


def load_research_overrides(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or _find_config("research_overrides.json")
    if not path or not path.exists():
        return {}
    payload = path.read_text(encoding="utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}
