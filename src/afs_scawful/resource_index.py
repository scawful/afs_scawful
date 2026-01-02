"""Resource discovery and indexing for AFS Scawful."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_training_resources
from .paths import resolve_index_root


DEFAULT_SEARCH_PATTERNS = [
    "**/*.asm",
    "**/*.md",
    "**/*.txt",
    "**/*.inc",
    "**/*.s",
    "**/*.65s",
    "**/*.65c",
    "**/*.c",
    "**/*.h",
    "**/*.cpp",
    "**/*.cc",
    "**/*.cs",
    "**/*.pdf",
]

DEFAULT_EXCLUDE_NAMES = {
    "node_modules",
    ".git",
    "build",
    "dist",
    "__pycache__",
    "venv",
    ".venv",
    "target",
}


@dataclass
class ResourceFile:
    path: Path
    file_type: str
    size_bytes: int
    last_modified: str
    content_hash: str
    source_dir: str
    relative_path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "last_modified": self.last_modified,
            "content_hash": self.content_hash,
            "source_dir": self.source_dir,
            "relative_path": self.relative_path,
            "metadata": self.metadata,
        }


@dataclass
class IndexResult:
    total_files: int
    by_type: dict[str, int]
    by_source: dict[str, int]
    files: list[ResourceFile]
    duplicates_found: int
    errors: list[str]
    duration_seconds: float
    indexed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "by_type": self.by_type,
            "by_source": self.by_source,
            "duplicates_found": self.duplicates_found,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "indexed_at": self.indexed_at,
        }


class ResourceIndexer:
    def __init__(
        self,
        *,
        index_path: Path | None = None,
        resource_roots: list[Path] | None = None,
        search_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        cfg = load_training_resources()
        config = cfg.get("resource_discovery", {}) if isinstance(cfg, dict) else {}

        self.resource_roots = resource_roots or _parse_paths(config.get("resource_roots"))
        self.search_patterns = search_patterns or _parse_patterns(
            config.get("search_patterns")
        )
        if not self.search_patterns:
            self.search_patterns = list(DEFAULT_SEARCH_PATTERNS)

        self.exclude_patterns = exclude_patterns or _parse_patterns(
            config.get("exclude_patterns")
        )

        self.index_path = index_path or _parse_index_path(config.get("index_path"))
        if self.index_path is None:
            self.index_path = resolve_index_root() / "resource_index.json"

        self._errors: list[str] = []
        self._hashes: set[str] = set()

    def build_index(self) -> IndexResult:
        start = datetime.now()
        files: list[ResourceFile] = []
        duplicates = 0

        for root in self.resource_roots:
            if not root.exists():
                self._errors.append(f"missing root: {root}")
                continue
            for pattern in self.search_patterns:
                for path in root.rglob(pattern):
                    if not path.is_file():
                        continue
                    if _should_exclude(path, self.exclude_patterns):
                        continue
                    resource = self._index_file(path, root)
                    if resource is None:
                        continue
                    if resource.content_hash and resource.content_hash in self._hashes:
                        duplicates += 1
                        continue
                    if resource.content_hash:
                        self._hashes.add(resource.content_hash)
                    files.append(resource)

        by_type: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for resource in files:
            by_type[resource.file_type] = by_type.get(resource.file_type, 0) + 1
            source_name = Path(resource.source_dir).name
            by_source[source_name] = by_source.get(source_name, 0) + 1

        duration = (datetime.now() - start).total_seconds()
        return IndexResult(
            total_files=len(files),
            by_type=by_type,
            by_source=by_source,
            files=files,
            duplicates_found=duplicates,
            errors=self._errors,
            duration_seconds=duration,
            indexed_at=datetime.now().isoformat(),
        )

    def write_index(self, result: IndexResult) -> Path:
        payload = {
            "metadata": result.to_dict(),
            "files": [item.to_dict() for item in result.files],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.index_path

    def load_index(self) -> IndexResult | None:
        if not self.index_path.exists():
            return None
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        files = [
            ResourceFile(
                path=Path(item["path"]),
                file_type=item["file_type"],
                size_bytes=item["size_bytes"],
                last_modified=item["last_modified"],
                content_hash=item.get("content_hash", ""),
                source_dir=item["source_dir"],
                relative_path=item["relative_path"],
                metadata=item.get("metadata", {}),
            )
            for item in payload.get("files", [])
        ]
        meta = payload.get("metadata", {})
        return IndexResult(
            total_files=meta.get("total_files", len(files)),
            by_type=meta.get("by_type", {}),
            by_source=meta.get("by_source", {}),
            files=files,
            duplicates_found=meta.get("duplicates_found", 0),
            errors=meta.get("errors", []),
            duration_seconds=meta.get("duration_seconds", 0.0),
            indexed_at=meta.get("indexed_at", ""),
        )

    def _index_file(self, path: Path, source_root: Path) -> ResourceFile | None:
        try:
            stat = path.stat()
        except OSError:
            self._errors.append(f"stat failed: {path}")
            return None

        file_type = _get_file_type(path)
        content_hash = _hash_file(path)
        relative = str(path.relative_to(source_root))
        return ResourceFile(
            path=path,
            file_type=file_type,
            size_bytes=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            content_hash=content_hash,
            source_dir=str(source_root),
            relative_path=relative,
        )


def _get_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    type_map = {
        ".asm": "asm",
        ".s": "asm",
        ".65s": "asm",
        ".65c": "asm",
        ".inc": "asm_include",
        ".md": "markdown",
        ".txt": "text",
        ".c": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".h": "header",
        ".cs": "csharp",
        ".pdf": "pdf",
    }
    return type_map.get(suffix, "unknown")


def _hash_file(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError:
        return ""
    return hashlib.md5(content).hexdigest()


def _should_exclude(path: Path, patterns: list[str] | None) -> bool:
    parts_lower = {part.lower() for part in path.parts}
    for name in DEFAULT_EXCLUDE_NAMES:
        if name.lower() in parts_lower:
            return True
    if not patterns:
        return False
    path_str = str(path)
    for pattern in patterns:
        if pattern and pattern in path_str:
            return True
    return False


def _parse_paths(raw: Any) -> list[Path]:
    if not raw:
        return []
    roots: list[Path] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, Path):
                roots.append(item)
                continue
            if isinstance(item, str):
                roots.append(Path(item).expanduser().resolve())
    return roots


def _parse_patterns(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def _parse_index_path(raw: Any) -> Path | None:
    if isinstance(raw, str) and raw:
        return Path(raw).expanduser().resolve()
    return None
