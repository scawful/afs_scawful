#!/usr/bin/env python3
"""
Generate prefix/FIM autocomplete datasets from 65816 assembly sources.
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_EXTENSIONS = {".asm", ".inc", ".s"}
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "out",
    "obj",
    "vendor",
    "third_party",
    "roms",
}


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def iter_source_files(
    roots: List[Path],
    extensions: set[str],
    exclude_dirs: set[str],
    max_files: int,
) -> Iterable[tuple[Path, Path]]:
    seen = 0
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name for name in dirnames
                if name not in exclude_dirs and not name.startswith(".")
            ]
            for filename in filenames:
                if max_files and seen >= max_files:
                    return
                path = Path(dirpath) / filename
                if path.suffix.lower() not in extensions:
                    continue
                seen += 1
                yield root, path


def pick_mode(rng: random.Random, mode: str, fim_rate: float) -> str:
    if mode == "mixed":
        return "fim" if rng.random() < fim_rate else "prefix"
    return mode


def sample_segments(
    lines: List[str],
    rng: random.Random,
    mode: str,
    min_prefix_lines: int,
    max_prefix_lines: int,
    min_completion_lines: int,
    max_completion_lines: int,
    min_suffix_lines: int,
    max_suffix_lines: int,
    max_prefix_chars: int,
    max_completion_chars: int,
    max_suffix_chars: int,
    min_completion_chars: int,
) -> Optional[tuple[str, str, str]]:
    if not lines:
        return None

    completion_len = rng.randint(min_completion_lines, max_completion_lines)
    suffix_len = 0
    if mode == "fim":
        suffix_len = rng.randint(min_suffix_lines, max_suffix_lines)

    min_total = min_prefix_lines + completion_len + suffix_len
    if len(lines) < min_total:
        return None

    max_start = len(lines) - completion_len - suffix_len
    if max_start <= min_prefix_lines:
        return None

    completion_start = rng.randint(min_prefix_lines, max_start)
    prefix_window = rng.randint(min_prefix_lines, max_prefix_lines)
    prefix_start = max(0, completion_start - prefix_window)
    prefix = "".join(lines[prefix_start:completion_start])
    completion = "".join(lines[completion_start:completion_start + completion_len])
    suffix = "".join(
        lines[completion_start + completion_len:completion_start + completion_len + suffix_len]
    )

    if max_prefix_chars and len(prefix) > max_prefix_chars:
        prefix = prefix[-max_prefix_chars:]
    if max_completion_chars and len(completion) > max_completion_chars:
        completion = completion[:max_completion_chars]
    if max_suffix_chars and len(suffix) > max_suffix_chars:
        suffix = suffix[:max_suffix_chars]

    if len(completion.strip()) < min_completion_chars:
        return None

    return prefix, completion, suffix


def default_roots(repo_root: Path) -> List[Path]:
    workspace_root = repo_root.parents[1]
    candidates = [
        workspace_root / "third_party" / "usdasm",
        workspace_root / "hobby" / "oracle-of-secrets",
        workspace_root / "hobby" / "zelda3",
        workspace_root / "hobby" / "alttp-65816",
        workspace_root / "hobby" / "alttp-hacker-workspace",
    ]
    return [path for path in candidates if path.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate autocomplete datasets.")
    parser.add_argument("--roots", nargs="*", type=Path, default=None, help="Source roots.")
    parser.add_argument("--train-out", type=Path, required=True, help="Output train JSONL.")
    parser.add_argument("--val-out", type=Path, required=True, help="Output val JSONL.")
    parser.add_argument("--mode", choices=["prefix", "fim", "mixed"], default="prefix")
    parser.add_argument("--fim-rate", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--samples-per-file", type=int, default=6)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--val-rate", type=float, default=0.02)
    parser.add_argument("--extensions", type=str, default=",".join(sorted(DEFAULT_EXTENSIONS)))
    parser.add_argument("--max-file-size", type=int, default=2_000_000)
    parser.add_argument("--min-prefix-lines", type=int, default=4)
    parser.add_argument("--max-prefix-lines", type=int, default=80)
    parser.add_argument("--min-completion-lines", type=int, default=1)
    parser.add_argument("--max-completion-lines", type=int, default=5)
    parser.add_argument("--min-suffix-lines", type=int, default=1)
    parser.add_argument("--max-suffix-lines", type=int, default=12)
    parser.add_argument("--max-prefix-chars", type=int, default=4000)
    parser.add_argument("--max-completion-chars", type=int, default=1200)
    parser.add_argument("--max-suffix-chars", type=int, default=2000)
    parser.add_argument("--min-completion-chars", type=int, default=8)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    roots = args.roots if args.roots else default_roots(repo_root)
    if not roots:
        raise SystemExit("No roots found. Pass --roots with valid paths.")

    extensions = {ext.strip().lower() for ext in args.extensions.split(",") if ext.strip()}
    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)

    rng = random.Random(args.seed)
    args.train_out.parent.mkdir(parents=True, exist_ok=True)
    args.val_out.parent.mkdir(parents=True, exist_ok=True)

    counts = {"train": 0, "val": 0, "files": 0}
    with args.train_out.open("w", encoding="utf-8") as train_handle, args.val_out.open(
        "w", encoding="utf-8"
    ) as val_handle:
        for root, path in iter_source_files(roots, extensions, exclude_dirs, args.max_files):
            try:
                if args.max_file_size and path.stat().st_size > args.max_file_size:
                    continue
                text = normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue

            lines = text.splitlines(keepends=True)
            if not lines:
                continue

            counts["files"] += 1
            attempts = args.samples_per_file * 3
            emitted = 0
            while emitted < args.samples_per_file and attempts > 0:
                attempts -= 1
                sample_mode = pick_mode(rng, args.mode, args.fim_rate)
                segments = sample_segments(
                    lines,
                    rng,
                    sample_mode,
                    args.min_prefix_lines,
                    args.max_prefix_lines,
                    args.min_completion_lines,
                    args.max_completion_lines,
                    args.min_suffix_lines,
                    args.max_suffix_lines,
                    args.max_prefix_chars,
                    args.max_completion_chars,
                    args.max_suffix_chars,
                    args.min_completion_chars,
                )
                if not segments:
                    continue

                prefix, completion, suffix = segments
                record = {
                    "prefix": prefix,
                    "completion": completion,
                    "suffix": suffix if sample_mode == "fim" else "",
                    "mode": sample_mode,
                    "language": "asm65816",
                    "project": root.name,
                    "source": str(path.relative_to(root)),
                }
                handle = val_handle if rng.random() < args.val_rate else train_handle
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                target = "val" if handle is val_handle else "train"
                counts[target] += 1
                emitted += 1
                if args.max_samples and (counts["train"] + counts["val"]) >= args.max_samples:
                    break
            if args.max_samples and (counts["train"] + counts["val"]) >= args.max_samples:
                break

    total = counts["train"] + counts["val"]
    print(f"Roots: {len(roots)} | Files scanned: {counts['files']}")
    print(f"Samples: {total} (train={counts['train']}, val={counts['val']})")
    print(f"Train -> {args.train_out}")
    print(f"Val   -> {args.val_out}")


if __name__ == "__main__":
    main()
