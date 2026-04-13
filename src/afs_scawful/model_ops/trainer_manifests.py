"""Trainer-facing helpers for building run manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .manifests import build_path_record, build_training_run_manifest


def tracked_input_record(
    value: str | Path | Mapping[str, Any] | None,
    *,
    include_rows: bool = False,
) -> dict[str, Any] | None:
    """Normalize a tracked input into a manifest record."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        if "record" in value:
            return dict(value["record"])
        if "path" not in value:
            return dict(value)
        include = bool(value.get("include_rows", include_rows))
        return build_path_record(value["path"], include_rows=include)
    return build_path_record(value, include_rows=include_rows)


def build_trainer_run_manifest(
    *,
    mode: str,
    trainer: str,
    model: str,
    output_dir: str | Path,
    data_dir: str | Path,
    hyperparameters: dict[str, Any],
    preset: str | None = None,
    command: list[str] | None = None,
    tracked_inputs: Mapping[str, str | Path | Mapping[str, Any] | None] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a manifest with conventional train/valid JSONL inputs."""

    data_root = Path(data_dir).expanduser().resolve(strict=False)
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in {
        "train_jsonl": data_root / "train.jsonl",
        "valid_jsonl": data_root / "valid.jsonl",
    }.items():
        if path.exists():
            inputs[key] = build_path_record(path, include_rows=True)

    for key, value in (tracked_inputs or {}).items():
        record = tracked_input_record(value)
        if record is not None:
            inputs[key] = record

    return build_training_run_manifest(
        mode=mode,
        trainer=trainer,
        preset=preset,
        model=model,
        output_dir=output_dir,
        data_dir=data_dir,
        hyperparameters=hyperparameters,
        command=command,
        inputs=inputs,
        metadata=metadata,
    )
