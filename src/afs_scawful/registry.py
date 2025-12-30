"""Dataset registry utilities for AFS Scawful."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import resolve_datasets_root, resolve_index_root


@dataclass
class DatasetEntry:
    name: str
    path: Path
    size_bytes: int
    updated_at: str
    files: list[str]
    stats: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "updated_at": self.updated_at,
            "files": list(self.files),
        }
        if self.stats:
            payload["stats"] = self.stats
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def build_dataset_registry(datasets_root: Path) -> dict[str, Any]:
    entries: list[DatasetEntry] = []
    if not datasets_root.exists():
        return {
            "generated_at": datetime.now().isoformat(),
            "datasets": [],
        }

    for entry in sorted(datasets_root.iterdir()):
        if entry.is_dir():
            dataset_entry = _build_dataset_entry(entry)
            if dataset_entry:
                entries.append(dataset_entry)
        elif entry.is_file() and entry.suffix.lower() in {".jsonl", ".json"}:
            dataset_entry = _build_file_dataset_entry(entry)
            if dataset_entry:
                entries.append(dataset_entry)

    return {
        "generated_at": datetime.now().isoformat(),
        "datasets": [entry.to_dict() for entry in entries],
    }


def write_dataset_registry(registry: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return output_path


def index_datasets(
    datasets_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    datasets_root = datasets_root or resolve_datasets_root()
    output_path = output_path or resolve_index_root() / "dataset_registry.json"
    registry = build_dataset_registry(datasets_root)
    return write_dataset_registry(registry, output_path)


def _build_dataset_entry(dataset_dir: Path) -> DatasetEntry | None:
    files = [file for file in dataset_dir.iterdir() if file.is_file()]
    if not files:
        return None

    known_files = {
        "train.jsonl",
        "val.jsonl",
        "validation.jsonl",
        "test.jsonl",
        "accepted.jsonl",
        "rejected.jsonl",
        "stats.json",
        "metadata.json",
        "user_annotations.json",
    }
    if not any(file.name in known_files for file in files):
        return None

    size_bytes = sum(file.stat().st_size for file in files)
    latest_mtime = max(file.stat().st_mtime for file in files)
    updated_at = datetime.fromtimestamp(latest_mtime).isoformat()
    stats = _load_json(dataset_dir / "stats.json")
    metadata = _load_json(dataset_dir / "metadata.json")

    return DatasetEntry(
        name=dataset_dir.name,
        path=dataset_dir,
        size_bytes=size_bytes,
        updated_at=updated_at,
        files=[file.name for file in files],
        stats=stats or None,
        metadata=metadata or None,
    )


def _build_file_dataset_entry(dataset_file: Path) -> DatasetEntry | None:
    size_bytes = dataset_file.stat().st_size
    updated_at = datetime.fromtimestamp(dataset_file.stat().st_mtime).isoformat()
    return DatasetEntry(
        name=dataset_file.stem,
        path=dataset_file,
        size_bytes=size_bytes,
        updated_at=updated_at,
        files=[dataset_file.name],
        stats=None,
        metadata=None,
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
