"""Generic track specifications for model operations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class TrackSpecError(ValueError):
    """Raised when a track spec is invalid."""


def _normalize_phase_spec(name: str, phase_spec: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(phase_spec)
    artifact_path = normalized.get("artifact_path") or normalized.get("merged_dir")
    if not artifact_path:
        raise TrackSpecError(f"phase {name!r} is missing artifact_path")
    normalized["artifact_path"] = artifact_path
    normalized.setdefault("title", name.replace("_", " ").title())
    return normalized


def get_phase_order(track_spec: dict[str, Any]) -> list[str]:
    """Return the ordered phase names for a track spec."""

    phase_order = track_spec.get("phase_order")
    if phase_order:
        return list(phase_order)
    phases = track_spec.get("phases", {})
    return list(phases.keys())


def validate_track_spec(track_spec: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a track spec."""

    phases = track_spec.get("phases")
    if not isinstance(phases, dict) or not phases:
        raise TrackSpecError("track spec must define a non-empty phases mapping")

    normalized = deepcopy(track_spec)
    normalized["phases"] = {
        name: _normalize_phase_spec(name, phase_spec)
        for name, phase_spec in phases.items()
    }
    phase_order = get_phase_order(normalized)
    missing = [name for name in phase_order if name not in normalized["phases"]]
    if missing:
        raise TrackSpecError(f"phase_order references unknown phases: {', '.join(missing)}")
    normalized["phase_order"] = phase_order
    normalized.setdefault("auto_start_commands", {})
    return normalized


def get_phase_spec(track_spec: dict[str, Any], phase_name: str) -> dict[str, Any]:
    """Return a normalized phase spec."""

    normalized = validate_track_spec(track_spec)
    try:
        return deepcopy(normalized["phases"][phase_name])
    except KeyError as exc:
        raise TrackSpecError(f"unknown phase: {phase_name}") from exc


def apply_track_overrides(track_spec: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply per-run overrides to a track spec."""

    normalized = validate_track_spec(track_spec)
    if not overrides:
        return normalized

    updated = deepcopy(normalized)
    phase_overrides = overrides.get("phase_overrides", {})
    for phase_name, phase_override in phase_overrides.items():
        if phase_name not in updated["phases"]:
            updated["phases"][phase_name] = {}
        updated["phases"][phase_name].update(phase_override)

    auto_start_commands = overrides.get("auto_start_commands", {})
    if auto_start_commands:
        updated.setdefault("auto_start_commands", {}).update(auto_start_commands)

    if overrides.get("phase_order"):
        updated["phase_order"] = list(overrides["phase_order"])
    if overrides.get("description"):
        updated["description"] = overrides["description"]
    return validate_track_spec(updated)
