#!/usr/bin/env python3
"""
OCR ingestion for PDFs and scanned images.

Outputs:
- text/   : extracted text files
- ocr/    : OCR-processed PDFs (if ocrmypdf is available)
- manifest.jsonl : metadata for every processed file
- failures.jsonl : failures with error details
- dataset.jsonl  : optional text-only dataset for later curation
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class ExtractResult:
    engine: str
    text_path: Path | None
    ocr_path: Path | None
    status: str
    error: str | None = None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def iter_files(root: Path, extensions: set[str]) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in extensions:
            yield path


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def run_cmd(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def extract_pdf(
    source: Path,
    text_path: Path,
    ocr_path: Path,
    lang: str,
    overwrite: bool,
    prefer_ocr: bool,
) -> ExtractResult:
    if text_path.exists() and not overwrite:
        return ExtractResult("skip", text_path, ocr_path if ocr_path.exists() else None, "skipped")

    text_path.parent.mkdir(parents=True, exist_ok=True)
    ocr_path.parent.mkdir(parents=True, exist_ok=True)

    if prefer_ocr and command_exists("ocrmypdf"):
        cmd = [
            "ocrmypdf",
            "--skip-text",
            "--sidecar",
            str(text_path),
            "--language",
            lang,
            str(source),
            str(ocr_path),
        ]
        run_cmd(cmd)
        return ExtractResult("ocrmypdf", text_path, ocr_path, "ok")

    if command_exists("pdftotext"):
        cmd = ["pdftotext", str(source), str(text_path)]
        run_cmd(cmd)
        return ExtractResult("pdftotext", text_path, None, "ok")

    return ExtractResult(
        "missing",
        None,
        None,
        "error",
        "missing ocrmypdf and pdftotext",
    )


def extract_image(
    source: Path,
    text_path: Path,
    lang: str,
    overwrite: bool,
) -> ExtractResult:
    if text_path.exists() and not overwrite:
        return ExtractResult("skip", text_path, None, "skipped")

    if not command_exists("tesseract"):
        return ExtractResult("missing", None, None, "error", "missing tesseract")

    text_path.parent.mkdir(parents=True, exist_ok=True)
    base = text_path.with_suffix("")
    cmd = ["tesseract", str(source), str(base), "-l", lang]
    run_cmd(cmd)
    if not text_path.exists():
        return ExtractResult("tesseract", None, None, "error", "tesseract output missing")
    return ExtractResult("tesseract", text_path, None, "ok")


def build_output_root(training_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return training_root / "raw" / "ocr" / stamp


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR ingest PDFs and images.")
    parser.add_argument("--input", required=True, type=Path, help="Input directory with PDFs/images.")
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Output root for OCR/text artifacts.",
    )
    parser.add_argument(
        "--training-root",
        type=Path,
        default=Path.home() / "src" / "training",
        help="Training root used when output-root is omitted.",
    )
    parser.add_argument("--lang", default="eng", help="OCR language (tesseract/ocrmypdf).")
    parser.add_argument(
        "--no-ocrmypdf",
        action="store_true",
        help="Disable ocrmypdf even if installed.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing OCR/text outputs.",
    )
    parser.add_argument(
        "--emit-dataset",
        action="store_true",
        help="Emit dataset.jsonl with extracted text.",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=200,
        help="Minimum text length for dataset entries.",
    )
    args = parser.parse_args()

    input_root = args.input.expanduser().resolve()
    if not input_root.exists():
        raise SystemExit(f"missing input root: {input_root}")

    training_root = args.training_root.expanduser().resolve()
    output_root = (
        args.output_root.expanduser().resolve()
        if args.output_root
        else build_output_root(training_root)
    )
    output_root.mkdir(parents=True, exist_ok=True)

    text_dir = output_root / "text"
    ocr_dir = output_root / "ocr"
    manifest_path = output_root / "manifest.jsonl"
    failures_path = output_root / "failures.jsonl"
    dataset_path = output_root / "dataset.jsonl" if args.emit_dataset else None

    prefer_ocr = not args.no_ocrmypdf
    extensions = PDF_EXTS | IMAGE_EXTS

    processed = 0
    failed = 0

    dataset_handle = dataset_path.open("a", encoding="utf-8") if dataset_path else None
    with manifest_path.open("a", encoding="utf-8") as manifest, failures_path.open(
        "a", encoding="utf-8"
    ) as failures:
        for source in iter_files(input_root, extensions):
            rel_path = source.relative_to(input_root)
            text_path = text_dir / rel_path.with_suffix(".txt")
            ocr_path = ocr_dir / rel_path if source.suffix.lower() == ".pdf" else None

            try:
                if source.suffix.lower() == ".pdf":
                    assert ocr_path is not None
                    result = extract_pdf(
                        source,
                        text_path,
                        ocr_path,
                        args.lang,
                        args.overwrite,
                        prefer_ocr,
                    )
                else:
                    result = extract_image(source, text_path, args.lang, args.overwrite)
            except subprocess.CalledProcessError as exc:
                result = ExtractResult(
                    "error",
                    None,
                    None,
                    "error",
                    f"command failed: {exc}",
                )

            record = {
                "created_at": now_iso(),
                "source_root": str(input_root),
                "source_path": str(source),
                "source_rel": str(rel_path),
                "file_type": "pdf" if source.suffix.lower() == ".pdf" else "image",
                "engine": result.engine,
                "text_path": str(result.text_path) if result.text_path else None,
                "ocr_path": str(result.ocr_path) if result.ocr_path else None,
                "status": result.status,
                "error": result.error,
                "sha256": sha256_path(source),
                "bytes": source.stat().st_size,
            }

            if result.status == "ok" and result.text_path and result.text_path.exists():
                text = normalize_text(result.text_path.read_text(encoding="utf-8", errors="ignore"))
                record["text_chars"] = len(text)
                if dataset_handle and len(text) >= args.min_chars:
                    dataset_entry = {
                        "text": text,
                        "source_path": str(source),
                        "source_rel": str(rel_path),
                        "created_at": record["created_at"],
                        "file_type": record["file_type"],
                        "engine": record["engine"],
                        "sha256": record["sha256"],
                    }
                    dataset_handle.write(json.dumps(dataset_entry, ensure_ascii=True) + "\n")
                processed += 1
            elif result.status == "skipped":
                processed += 1
            else:
                failed += 1
                failures.write(json.dumps(record, ensure_ascii=True) + "\n")

            manifest.write(json.dumps(record, ensure_ascii=True) + "\n")
    if dataset_handle:
        dataset_handle.close()

    print(f"output_root: {output_root}")
    print(f"processed: {processed}")
    print(f"failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
