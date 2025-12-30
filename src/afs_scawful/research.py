"""Research catalog utilities for AFS Scawful."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import load_research_paths

try:  # Optional dependency for richer metadata extraction.
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional import
    PdfReader = None


_PDF_FIELDS = ("Title", "Author", "Subject", "Keywords")


def default_research_root() -> Path:
    candidates = [
        Path.home() / "Documents" / "Research",
        Path.home() / "Documents" / "research",
        Path.home() / "Research",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_research_root(config_path: Path | None = None) -> Path:
    env_value = os.getenv("AFS_RESEARCH_ROOT")
    if env_value:
        return Path(env_value).expanduser().resolve()
    data = load_research_paths(config_path=config_path)
    paths = data.get("paths", {}) if isinstance(data, dict) else {}
    root = paths.get("research_root") or paths.get("research")
    if isinstance(root, Path):
        return root
    if isinstance(root, str) and root:
        return Path(root).expanduser().resolve()
    return default_research_root()


def resolve_research_catalog_path(config_path: Path | None = None) -> Path:
    env_value = os.getenv("AFS_RESEARCH_CATALOG")
    if env_value:
        return Path(env_value).expanduser().resolve()
    data = load_research_paths(config_path=config_path)
    paths = data.get("paths", {}) if isinstance(data, dict) else {}
    catalog = paths.get("research_catalog") or paths.get("catalog")
    if isinstance(catalog, Path):
        return catalog
    if isinstance(catalog, str) and catalog:
        return Path(catalog).expanduser().resolve()
    return Path.home() / "src" / "context" / "index" / "research_catalog.json"


def iter_pdf_paths(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    paths: list[Path] = []
    for path in root.rglob("*.pdf"):
        if any(part.startswith(".") for part in path.parts):
            continue
        paths.append(path)
    return sorted(paths)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return slug.strip("-")


def make_paper_id(relative_path: Path) -> str:
    stem = relative_path.with_suffix("").as_posix()
    slug = _slugify(stem)
    digest = hashlib.sha1(relative_path.as_posix().encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}" if slug else digest


def _normalize_meta_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return " ".join(text.split())


def _parse_pdf_literal(value: bytes) -> str:
    text = value.decode("latin-1", errors="ignore")
    text = text.replace("\\(", "(").replace("\\)", ")")
    text = text.replace("\\n", " ").replace("\\r", " ")
    return " ".join(text.split()).strip()


def _read_pdf_snippet(path: Path, limit_bytes: int = 2_000_000) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit_bytes)


def _has_pdf_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def _extract_metadata_regex(path: Path) -> dict[str, str]:
    data = _read_pdf_snippet(path)
    meta: dict[str, str] = {}
    for field in _PDF_FIELDS:
        pattern = re.compile(rb"/" + field.encode("ascii") + rb"\s*\(([^)]{0,512})\)", re.IGNORECASE | re.DOTALL)
        match = pattern.search(data)
        if match:
            meta[field.lower()] = _parse_pdf_literal(match.group(1))
    return meta


def extract_abstract_excerpt(text: str, max_chars: int = 1200) -> str | None:
    if not text:
        return None
    match = re.search(r"\bAbstract\b", text, re.IGNORECASE)
    if not match:
        return None
    snippet = text[match.end():].lstrip(":\n\r\t ")
    end = re.search(r"\n\s*(?:\d+\s+Introduction|Introduction|Keywords|Index Terms|1\.|I\.)", snippet)
    if end:
        snippet = snippet[: end.start()]
    snippet = " ".join(snippet.split()).strip()
    if not snippet:
        return None
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip() + "..."
    return snippet


def _extract_metadata_pypdf(
    path: Path,
    include_abstract: bool,
    max_pages: int,
    max_abstract_chars: int,
) -> tuple[dict[str, str | None], int | None, str | None]:
    if PdfReader is None:
        raise RuntimeError("pypdf not available")
    reader = PdfReader(str(path))
    metadata = reader.metadata or {}
    values = {
        "title": _normalize_meta_value(metadata.get("/Title") or metadata.get("Title")),
        "author": _normalize_meta_value(metadata.get("/Author") or metadata.get("Author")),
        "subject": _normalize_meta_value(metadata.get("/Subject") or metadata.get("Subject")),
        "keywords": _normalize_meta_value(metadata.get("/Keywords") or metadata.get("Keywords")),
    }
    abstract_excerpt = None
    if include_abstract:
        page_text: list[str] = []
        for page in reader.pages[:max_pages]:
            try:
                page_text.append(page.extract_text() or "")
            except Exception:
                page_text.append("")
        abstract_excerpt = extract_abstract_excerpt("\n".join(page_text), max_chars=max_abstract_chars)
    return values, len(reader.pages), abstract_excerpt


def build_paper_entry(
    path: Path,
    root: Path,
    include_abstract: bool = True,
    max_pages: int = 2,
    max_abstract_chars: int = 1200,
) -> dict[str, object]:
    relative_path = path.relative_to(root)
    entry = {
        "id": make_paper_id(relative_path),
        "path": str(path),
        "relative_path": relative_path.as_posix(),
        "filename": path.name,
        "title": None,
        "author": None,
        "subject": None,
        "keywords": None,
        "page_count": None,
        "file_size": path.stat().st_size,
        "modified_time": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "abstract_excerpt": None,
        "abstract_source": "none",
        "metadata_source": "none",
    }

    metadata: dict[str, str | None] = {}
    page_count = None
    abstract_excerpt = None
    if PdfReader is not None and _has_pdf_header(path):
        try:
            metadata, page_count, abstract_excerpt = _extract_metadata_pypdf(
                path,
                include_abstract=include_abstract,
                max_pages=max_pages,
                max_abstract_chars=max_abstract_chars,
            )
            entry["metadata_source"] = "pypdf"
        except Exception:
            metadata = {}
    if not metadata:
        metadata = _extract_metadata_regex(path)
        if metadata:
            entry["metadata_source"] = "regex"

    for key, value in metadata.items():
        if value:
            entry[key] = value
    if page_count:
        entry["page_count"] = page_count
    if abstract_excerpt:
        entry["abstract_excerpt"] = abstract_excerpt
        entry["abstract_source"] = "pypdf"
    return entry


def build_research_catalog(
    root: Path,
    include_abstract: bool = True,
    max_pages: int = 2,
    max_abstract_chars: int = 1200,
) -> dict[str, object]:
    papers: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for path in iter_pdf_paths(root):
        try:
            entry = build_paper_entry(
                path,
                root=root,
                include_abstract=include_abstract,
                max_pages=max_pages,
                max_abstract_chars=max_abstract_chars,
            )
        except Exception as exc:  # pragma: no cover - defensive
            errors.append({"path": str(path), "error": str(exc)})
            continue
        papers.append(entry)

    catalog: dict[str, object] = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "count": len(papers),
        "papers": papers,
    }
    if errors:
        catalog["errors"] = errors
    return catalog


def write_research_catalog(catalog: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_research_catalog(path: Path) -> dict[str, object]:
    payload = path.read_text(encoding="utf-8")
    return json.loads(payload)


def resolve_paper_path(catalog: dict[str, object], paper_id: str) -> Path | None:
    candidate_path = Path(paper_id).expanduser()
    if candidate_path.exists():
        return candidate_path.resolve()

    root_value = catalog.get("root")
    root = Path(root_value).expanduser().resolve() if root_value else None
    for entry in catalog.get("papers", []):
        if not isinstance(entry, dict):
            continue
        if paper_id in (entry.get("id"), entry.get("filename"), entry.get("relative_path")):
            if root is None:
                return Path(entry.get("path", "")).expanduser().resolve()
            return (root / entry.get("relative_path", "")).expanduser().resolve()
    return None


def open_pdf(path: Path) -> bool:
    if sys.platform == "darwin":
        command = ["open", str(path)]
    elif os.name == "nt":
        command = ["cmd", "/c", "start", "", str(path)]
    else:
        command = ["xdg-open", str(path)]
    try:
        subprocess.run(command, check=False)
    except FileNotFoundError:
        return False
    return True
