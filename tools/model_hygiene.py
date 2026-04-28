#!/usr/bin/env python3
"""Report local model hygiene across AFS, LM Studio, and ~/models."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "chat_registry.toml"
DEFAULT_MODELS_ROOT = Path.home() / "models"
DEFAULT_LMSTUDIO_INDEX = Path.home() / ".lmstudio" / ".internal" / "model-index-cache.json"
DEFAULT_LMSTUDIO_MODEL_DATA = Path.home() / ".lmstudio" / ".internal" / "model-data.json"


@dataclass(frozen=True)
class RegistryEntry:
    name: str
    provider: str
    model_id: str
    tags: tuple[str, ...] = ()
    role: str = ""


@dataclass(frozen=True)
class IndexedModel:
    indexed_model_identifier: str
    identifiers: frozenset[str]
    abs_path: str | None
    size_bytes: int
    display_name: str
    last_loaded_ms: int | None


@dataclass
class FileGroup:
    canonical_path: str
    all_paths: list[str]
    size_bytes: int
    link_count: int
    registry_names: list[str] = field(default_factory=list)
    indexed_identifiers: list[str] = field(default_factory=list)
    last_loaded_ms: int | None = None
    tier: str = "review"
    reason: str = ""


def load_registry(path: Path) -> list[RegistryEntry]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[RegistryEntry] = []
    for item in payload.get("models", []):
        name = str(item.get("name", "")).strip()
        model_id = str(item.get("model_id", "")).strip()
        if not name or not model_id:
            continue
        entries.append(
            RegistryEntry(
                name=name,
                provider=str(item.get("provider", "ollama")).strip(),
                model_id=model_id,
                tags=tuple(str(tag) for tag in (item.get("tags") or [])),
                role=str(item.get("role", "")).strip(),
            )
        )
    return entries


def load_last_loaded_map(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("json", [])
    last_loaded: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            continue
        key, meta = row
        if not isinstance(key, str) or not isinstance(meta, dict):
            continue
        value = meta.get("lastLoadedTimestamp")
        if isinstance(value, int):
            last_loaded[key] = value
    return last_loaded


def load_indexed_models(path: Path, last_loaded_map: dict[str, int]) -> list[IndexedModel]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[IndexedModel] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        indexed_id = str(item.get("indexedModelIdentifier", "")).strip()
        entry_point = item.get("entryPoint") or {}
        abs_path = entry_point.get("absPath")
        identifiers: set[str] = set()
        for key in ("indexedModelIdentifier", "defaultIdentifier", "altIndexedModelIdentifier"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                identifiers.add(value.strip())
        auto_ids = item.get("autoIdentifiers") or []
        if isinstance(auto_ids, list):
            for value in auto_ids:
                if isinstance(value, str) and value.strip():
                    identifiers.add(value.strip())
        if abs_path and isinstance(abs_path, str):
            identifiers.add(abs_path)

        last_loaded_ms = None
        for key in identifiers:
            ts = last_loaded_map.get(key)
            if ts is None:
                continue
            last_loaded_ms = max(last_loaded_ms or ts, ts)

        entries.append(
            IndexedModel(
                indexed_model_identifier=indexed_id,
                identifiers=frozenset(identifiers),
                abs_path=abs_path if isinstance(abs_path, str) else None,
                size_bytes=int(item.get("sizeBytes") or entry_point.get("sizeBytes") or 0),
                display_name=str(item.get("displayName", "")).strip(),
                last_loaded_ms=last_loaded_ms,
            )
        )
    return entries


def _prefer_canonical_path(paths: list[Path]) -> Path:
    def rank(path: Path) -> tuple[int, int, str]:
        text = str(path)
        penalty = 1 if "/lmstudio/" in text else 0
        return (penalty, len(text), text)

    return min(paths, key=rank)


def scan_file_groups(models_root: Path) -> list[FileGroup]:
    grouped: dict[tuple[int, int], list[Path]] = {}
    for path in sorted(models_root.rglob("*.gguf")):
        if path.name.endswith(".bak"):
            continue
        stat = path.stat()
        grouped.setdefault((stat.st_dev, stat.st_ino), []).append(path)

    groups: list[FileGroup] = []
    for paths in grouped.values():
        canonical = _prefer_canonical_path(paths)
        stat = canonical.stat()
        groups.append(
            FileGroup(
                canonical_path=str(canonical),
                all_paths=[str(path) for path in sorted(paths)],
                size_bytes=stat.st_size,
                link_count=stat.st_nlink,
            )
        )
    return sorted(groups, key=lambda group: group.canonical_path)


def _human_size(size_bytes: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def _format_timestamp(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _model_id_path(model_id: str, models_root: Path) -> Path | None:
    if model_id.startswith("gguf/"):
        return models_root / model_id
    if model_id.endswith(".gguf"):
        candidate = Path(model_id)
        return candidate if candidate.is_absolute() else models_root / candidate
    return None


def classify_registry(
    registry_entries: list[RegistryEntry],
    indexed_models: list[IndexedModel],
    models_root: Path,
) -> list[dict[str, Any]]:
    index_by_identifier: dict[str, IndexedModel] = {}
    for model in indexed_models:
        for identifier in model.identifiers:
            index_by_identifier.setdefault(identifier, model)
        if model.abs_path:
            index_by_identifier.setdefault(model.abs_path, model)

    results: list[dict[str, Any]] = []
    for entry in registry_entries:
        indexed = index_by_identifier.get(entry.model_id)
        candidate_path = _model_id_path(entry.model_id, models_root)
        resolved_path = Path(indexed.abs_path) if indexed and indexed.abs_path else candidate_path
        path_exists = resolved_path.exists() if resolved_path else False
        if indexed and path_exists:
            status = "healthy"
        elif indexed and not path_exists:
            status = "missing_file"
        elif candidate_path and path_exists:
            status = "missing_lmstudio_index"
        else:
            status = "unresolved"
        results.append(
            {
                "name": entry.name,
                "provider": entry.provider,
                "model_id": entry.model_id,
                "tags": list(entry.tags),
                "role": entry.role,
                "status": status,
                "resolved_path": str(resolved_path) if resolved_path else None,
                "path_exists": path_exists,
                "indexed": indexed is not None,
                "display_name": indexed.display_name if indexed else None,
                "last_loaded": _format_timestamp(indexed.last_loaded_ms if indexed else None),
            }
        )
    return sorted(results, key=lambda row: (row["provider"], row["name"]))


def annotate_groups(
    groups: list[FileGroup],
    registry_entries: list[RegistryEntry],
    indexed_models: list[IndexedModel],
    models_root: Path,
    stale_days: int,
    now_ms: int,
) -> list[FileGroup]:
    group_by_path: dict[str, FileGroup] = {}
    for group in groups:
        for path in group.all_paths:
            group_by_path[path] = group

    for entry in registry_entries:
        candidate_path = _model_id_path(entry.model_id, models_root)
        indexed = next((model for model in indexed_models if entry.model_id in model.identifiers), None)
        path: str | None = None
        if indexed and indexed.abs_path:
            path = indexed.abs_path
        elif candidate_path and candidate_path.exists():
            path = str(candidate_path)
        if not path:
            continue
        group = group_by_path.get(path)
        if not group:
            continue
        if entry.name not in group.registry_names:
            group.registry_names.append(entry.name)

    for model in indexed_models:
        if not model.abs_path:
            continue
        group = group_by_path.get(model.abs_path)
        if not group:
            continue
        group.indexed_identifiers.extend(
            identifier for identifier in sorted(model.identifiers) if identifier not in group.indexed_identifiers
        )
        if model.last_loaded_ms is not None:
            group.last_loaded_ms = max(group.last_loaded_ms or model.last_loaded_ms, model.last_loaded_ms)

    stale_ms = stale_days * 24 * 60 * 60 * 1000
    for group in groups:
        if group.registry_names:
            group.tier = "keep"
            group.reason = f"referenced by registry: {', '.join(sorted(group.registry_names))}"
            continue
        in_archive_tree = "/archive/" in group.canonical_path
        if group.last_loaded_ms is None:
            group.tier = "archive"
            group.reason = "not referenced by registry and never loaded in LM Studio"
            if in_archive_tree:
                group.reason += "; already lives under archive/"
            continue
        age_ms = now_ms - group.last_loaded_ms
        if in_archive_tree or age_ms >= stale_ms:
            group.tier = "archive"
            if in_archive_tree:
                group.reason = "not referenced by registry and already stored under archive/"
            else:
                days = max(1, age_ms // (24 * 60 * 60 * 1000))
                group.reason = f"not referenced by registry and last loaded {days} days ago"
        else:
            group.tier = "review"
            days = max(0, age_ms // (24 * 60 * 60 * 1000))
            group.reason = f"not referenced by registry but loaded recently ({days} days ago)"
    return groups


def build_report(
    registry_path: Path,
    models_root: Path,
    lmstudio_index_path: Path,
    lmstudio_model_data_path: Path,
    stale_days: int,
) -> dict[str, Any]:
    registry_entries = load_registry(registry_path)
    last_loaded_map = load_last_loaded_map(lmstudio_model_data_path)
    indexed_models = load_indexed_models(lmstudio_index_path, last_loaded_map)
    groups = scan_file_groups(models_root)
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    registry_status = classify_registry(registry_entries, indexed_models, models_root)
    local_entries = annotate_groups(groups, registry_entries, indexed_models, models_root, stale_days, now_ms)
    local_registry_rows = [row for row in registry_status if row["provider"] == "studio"]

    local_only = [group for group in local_entries if not group.registry_names]
    archive_candidates = [group for group in local_entries if group.tier == "archive"]

    summary = {
        "registry_models": len(registry_entries),
        "registry_local_models": sum(1 for entry in registry_entries if entry.provider == "studio"),
        "registry_nonlocal_models": sum(1 for entry in registry_entries if entry.provider != "studio"),
        "healthy_local_registry_models": sum(1 for row in local_registry_rows if row["status"] == "healthy"),
        "local_registry_models_missing_file": sum(1 for row in local_registry_rows if row["status"] == "missing_file"),
        "local_registry_models_missing_lmstudio_index": sum(
            1 for row in local_registry_rows if row["status"] == "missing_lmstudio_index"
        ),
        "local_registry_models_unresolved": sum(1 for row in local_registry_rows if row["status"] == "unresolved"),
        "unique_local_gguf_files": len(local_entries),
        "unregistered_local_files": len(local_only),
        "archive_candidates": len(archive_candidates),
    }

    return {
        "sources": {
            "registry_path": str(registry_path),
            "models_root": str(models_root),
            "lmstudio_index_path": str(lmstudio_index_path),
            "lmstudio_model_data_path": str(lmstudio_model_data_path),
            "hostname": os.uname().nodename,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stale_days": stale_days,
        },
        "summary": summary,
        "registry": registry_status,
        "local_only": [asdict(group) for group in sorted(local_only, key=lambda item: (-item.size_bytes, item.canonical_path))],
        "archive_candidates": [
            asdict(group) for group in sorted(archive_candidates, key=lambda item: (-item.size_bytes, item.canonical_path))
        ],
    }


def print_text_report(report: dict[str, Any], limit: int) -> None:
    summary = report["summary"]
    print("Model Hygiene Report")
    print(f"generated: {report['sources']['generated_at']}")
    print(f"registry:  {report['sources']['registry_path']}")
    print(f"models:    {report['sources']['models_root']}")
    print(f"lmstudio:  {report['sources']['lmstudio_index_path']}")
    print()
    print("Summary")
    print(f"- registry local models: {summary['registry_local_models']}")
    print(f"- registry nonlocal models: {summary['registry_nonlocal_models']}")
    print(f"- healthy local registry models: {summary['healthy_local_registry_models']}")
    print(f"- local missing file: {summary['local_registry_models_missing_file']}")
    print(f"- local missing LM Studio index: {summary['local_registry_models_missing_lmstudio_index']}")
    print(f"- local unresolved registry models: {summary['local_registry_models_unresolved']}")
    print(f"- unique local gguf files: {summary['unique_local_gguf_files']}")
    print(f"- unregistered local files: {summary['unregistered_local_files']}")
    print(f"- archive candidates: {summary['archive_candidates']}")

    problems = [
        row for row in report["registry"] if row["status"] != "healthy" and row["provider"] == "studio"
    ]
    if problems:
        print()
        print("Registry Problems")
        for row in problems[:limit]:
            print(
                f"- {row['name']}: {row['status']} "
                f"(model_id={row['model_id']}, path={row['resolved_path'] or 'n/a'})"
            )

    candidates = report["archive_candidates"]
    if candidates:
        print()
        print("Archive Candidates")
        for row in candidates[:limit]:
            last_loaded = _format_timestamp(row["last_loaded_ms"])
            print(
                f"- {row['canonical_path']} [{_human_size(row['size_bytes'])}]"
                f" last_loaded={last_loaded or 'never'}"
            )
            print(f"  reason: {row['reason']}")

    reviews = [row for row in report["local_only"] if row["tier"] == "review"]
    if reviews:
        print()
        print("Review Candidates")
        for row in reviews[:limit]:
            last_loaded = _format_timestamp(row["last_loaded_ms"])
            print(
                f"- {row['canonical_path']} [{_human_size(row['size_bytes'])}]"
                f" last_loaded={last_loaded or 'never'}"
            )
            print(f"  reason: {row['reason']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report local model hygiene for AFS + LM Studio")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--models-root", type=Path, default=DEFAULT_MODELS_ROOT)
    parser.add_argument("--lmstudio-index", type=Path, default=DEFAULT_LMSTUDIO_INDEX)
    parser.add_argument("--lmstudio-model-data", type=Path, default=DEFAULT_LMSTUDIO_MODEL_DATA)
    parser.add_argument("--stale-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        registry_path=args.registry,
        models_root=args.models_root,
        lmstudio_index_path=args.lmstudio_index,
        lmstudio_model_data_path=args.lmstudio_model_data,
        stale_days=args.stale_days,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_text_report(report, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
