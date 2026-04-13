"""Declarative bundle builders for remote training runs."""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Any, TypedDict


class BundleSpecError(ValueError):
    """Raised when a bundle spec is invalid."""


class BundleEntry(TypedDict):
    source: str
    arcname: str


class BundleSelection(TypedDict):
    required_paths: list[str]
    optional_paths: list[str]
    all_paths: list[str]
    entries: list[BundleEntry]


def _normalize_entry(root_dir: Path, entry: str | Path | dict[str, Any]) -> BundleEntry:
    if isinstance(entry, (str, Path)):
        raw_path = str(entry)
        source = Path(raw_path)
        if not source.is_absolute():
            source = root_dir / source
        return {"source": str(source), "arcname": raw_path}
    if isinstance(entry, dict) and entry.get("path"):
        source = Path(str(entry["path"]))
        if not source.is_absolute():
            source = root_dir / source
        arcname = entry.get("arcname") or str(entry["path"])
        return {"source": str(source), "arcname": str(arcname)}
    raise BundleSpecError(f"unsupported bundle entry: {entry!r}")


def normalize_bundle_spec(root_dir: Path, spec: dict[str, Any]) -> dict[str, list[BundleEntry]]:
    """Normalize a bundle spec into required and optional path lists."""

    normalized = {
        "required_paths": [_normalize_entry(root_dir, entry) for entry in spec.get("required_paths", [])],
        "optional_paths": [_normalize_entry(root_dir, entry) for entry in spec.get("optional_paths", [])],
    }
    if not normalized["required_paths"]:
        raise BundleSpecError("bundle spec must include at least one required path")
    return normalized


def validate_bundle_paths(root_dir: Path, spec: dict[str, Any]) -> BundleSelection:
    """Validate required bundle paths and collect existing optional paths."""

    normalized = normalize_bundle_spec(root_dir, spec)
    missing_required: list[str] = []
    included_required: list[str] = []
    included_optional: list[str] = []
    entries: list[BundleEntry] = []

    for item in normalized["required_paths"]:
        path = Path(item["source"])
        if path.exists():
            included_required.append(item["arcname"])
            entries.append(item)
        else:
            missing_required.append(item["arcname"])

    if missing_required:
        raise BundleSpecError(f"missing required bundle paths: {', '.join(missing_required)}")

    for item in normalized["optional_paths"]:
        if Path(item["source"]).exists():
            included_optional.append(item["arcname"])
            entries.append(item)

    return {
        "required_paths": included_required,
        "optional_paths": included_optional,
        "all_paths": included_required + included_optional,
        "entries": entries,
    }


def build_bundle(root_dir: Path, output_path: Path, spec: dict[str, Any]) -> list[str]:
    """Build a gzipped tar bundle from a declarative spec."""

    root_dir = root_dir.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    selected = validate_bundle_paths(root_dir, spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:gz") as archive:
        for entry in selected["entries"]:
            archive.add(Path(entry["source"]), arcname=entry["arcname"])
    return selected["all_paths"]
