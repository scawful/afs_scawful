"""Generic training run manifest helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    """Return an ISO8601 UTC timestamp without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    """Return the sha256 hash of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl_rows(path: Path) -> int:
    """Count non-empty rows in a JSONL file."""

    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def build_path_record(path: str | Path, *, include_rows: bool = False) -> dict[str, Any]:
    """Build a manifest record for a tracked file path."""

    resolved = _normalize_path(path)
    record: dict[str, Any] = {"path": str(resolved)}
    if not resolved.exists() or not resolved.is_file():
        return record

    record["sha256"] = sha256_file(resolved)
    if include_rows and resolved.suffix == ".jsonl":
        record["rows"] = count_jsonl_rows(resolved)
    return record


def write_run_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write a manifest to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_run_manifest(path: Path) -> dict[str, Any]:
    """Load a manifest from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def build_training_run_manifest(
    *,
    mode: str,
    model: str,
    output_dir: str | Path,
    data_dir: str | Path,
    hyperparameters: dict[str, Any],
    trainer: str | None = None,
    preset: str | None = None,
    command: list[str] | None = None,
    inputs: dict[str, dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a generic training run manifest."""

    manifest: dict[str, Any] = {
        "status": "running",
        "created_at": now_utc(),
        "mode": mode,
        "model": model,
        "output_dir": str(_normalize_path(output_dir)),
        "data_dir": str(_normalize_path(data_dir)),
        "hyperparameters": dict(hyperparameters),
        "artifacts": {},
        "inputs": dict(inputs or {}),
    }
    if trainer:
        manifest["trainer"] = trainer
    if preset:
        manifest["preset"] = preset
    if command:
        manifest["command"] = list(command)
    if metadata:
        manifest["metadata"] = dict(metadata)
    return manifest


def mark_manifest_failed(manifest: dict[str, Any], error: str) -> dict[str, Any]:
    """Mark a manifest as failed."""

    manifest["status"] = "failed"
    manifest["failed_at"] = now_utc()
    manifest["error"] = error
    return manifest


def mark_manifest_completed(
    manifest: dict[str, Any],
    *,
    artifacts: dict[str, str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark a manifest as completed."""

    manifest["status"] = "completed"
    manifest["completed_at"] = now_utc()
    if artifacts:
        manifest.setdefault("artifacts", {}).update(artifacts)
    if metrics:
        manifest.setdefault("metrics", {}).update(metrics)
    return manifest
