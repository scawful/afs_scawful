#!/usr/bin/env python3
"""Import essay files from Google Drive CLI and emit a local manifest."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("data/raw/essays_gdrive")
DEFAULT_MANIFEST = Path("data/training_data/essays_gdrive_manifest_v1.jsonl")
DEFAULT_RAW_TEXT_JSONL = Path("data/training_data/essays_gdrive_raw_v1.jsonl")

DEFAULT_QUERY = (
    "trashed = false and "
    "(name contains 'essay' or name contains 'draft' or name contains 'writing') and "
    "("
    "mimeType = 'application/vnd.google-apps.document' or "
    "mimeType = 'text/plain' or "
    "mimeType = 'text/markdown' or "
    "mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
    ")"
)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
GDRIVE_DOC_MIME = "application/vnd.google-apps.document"


def _run(cmd: list[str], *, timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip()
    safe = safe.rstrip(".")
    return safe or "untitled"


def _parse_list_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) >= 2:
        file_id = parts[0].strip()
        name = parts[1].strip()
        mime = parts[2].strip() if len(parts) >= 3 else ""
        return {"id": file_id, "name": name, "mime": mime}
    # Fallback for non-tab-separated output.
    tokens = line.split()
    if len(tokens) < 2:
        return None
    return {"id": tokens[0], "name": " ".join(tokens[1:]), "mime": ""}


def _list_files(query: str, parent: str | None, max_files: int) -> list[dict[str, str]]:
    cmd = [
        "gdrive",
        "files",
        "list",
        "--max",
        str(max_files),
        "--query",
        query,
        "--skip-header",
        "--full-name",
        "--field-separator",
        "\t",
    ]
    if parent:
        cmd += ["--parent", parent]

    try:
        proc = _run(cmd, timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "gdrive files list timed out (likely waiting for OAuth authorization). "
            "Run `gdrive account add` first."
        ) from exc

    output = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = f"{output}\n{err}".lower()
    if "open the url in your browser" in combined:
        raise RuntimeError(
            "gdrive needs interactive OAuth consent. Run `gdrive account add` and complete auth."
        )
    if "address already in use" in combined:
        raise RuntimeError(
            "gdrive OAuth listener is already bound (os error 48). "
            "Close any in-progress `gdrive account add` flow and retry."
        )
    if proc.returncode != 0:
        raise RuntimeError(f"gdrive list failed: {err or output or 'unknown error'}")

    rows: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        parsed = _parse_list_line(raw_line)
        if parsed:
            rows.append(parsed)
    return rows


def _download_or_export(entry: dict[str, str], output_dir: Path, overwrite: bool) -> tuple[str, str]:
    file_id = entry["id"]
    name = entry["name"]
    mime = entry.get("mime", "")
    safe_name = _sanitize_filename(name)

    if mime == GDRIVE_DOC_MIME:
        out_path = output_dir / f"{safe_name}.txt"
        cmd = ["gdrive", "files", "export", file_id, str(out_path)]
        if overwrite:
            cmd.insert(3, "--overwrite")
        proc = _run(cmd)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "export failed").strip())
        return "exported", str(out_path)

    ext = Path(safe_name).suffix.lower()
    if not ext:
        ext = ".txt" if "text/" in mime else ""
    target_name = safe_name if Path(safe_name).suffix else f"{safe_name}{ext}"
    out_path = output_dir / target_name

    cmd = [
        "gdrive",
        "files",
        "download",
        file_id,
        "--destination",
        str(output_dir),
    ]
    if overwrite:
        cmd.insert(3, "--overwrite")
    proc = _run(cmd)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "download failed").strip())
    return "downloaded", str(out_path)


def _maybe_load_text(path: Path, max_chars: int) -> str | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    return text[:max_chars]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import essays from Google Drive using gdrive CLI")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Drive query for files list")
    parser.add_argument("--parent", help="Optional parent folder id")
    parser.add_argument("--max-files", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-text-jsonl", type=Path, default=DEFAULT_RAW_TEXT_JSONL)
    parser.add_argument("--max-text-chars", type=int, default=12000)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        entries = _list_files(query=args.query, parent=args.parent, max_files=args.max_files)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    if not entries:
        print("no files matched query")
        return 0

    manifest_rows: list[dict[str, Any]] = []
    text_rows: list[dict[str, Any]] = []

    for entry in entries:
        row: dict[str, Any] = {
            "id": entry["id"],
            "name": entry["name"],
            "mime": entry.get("mime", ""),
            "status": "skipped",
            "path": None,
            "error": None,
        }
        try:
            status, out_path = _download_or_export(entry, output_dir=output_dir, overwrite=args.overwrite)
            row["status"] = status
            row["path"] = out_path
            text = _maybe_load_text(Path(out_path), max_chars=args.max_text_chars)
            if text:
                text_rows.append(
                    {
                        "title": entry["name"],
                        "path": out_path,
                        "text": text,
                        "_meta": {
                            "source": "gdrive_essay_import",
                            "file_id": entry["id"],
                            "mime": entry.get("mime", ""),
                        },
                    }
                )
        except Exception as exc:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = str(exc)
        manifest_rows.append(row)

    manifest_path = args.manifest.expanduser().resolve()
    _write_jsonl(manifest_path, manifest_rows)

    raw_text_path = args.raw_text_jsonl.expanduser().resolve()
    _write_jsonl(raw_text_path, text_rows)

    print(f"matched_files={len(entries)}")
    print(f"manifest_rows={len(manifest_rows)} -> {manifest_path}")
    print(f"text_rows={len(text_rows)} -> {raw_text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
