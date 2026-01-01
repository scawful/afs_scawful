#!/usr/bin/env python3
"""
Generate ASM training samples from comment headers near routine labels.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


LABEL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)::?\s*$")
COMMENT_RE = re.compile(r"^\s*;")


@dataclass
class Sample:
    label: str
    description: str
    code: str
    source: str


def is_label(line: str) -> bool:
    match = LABEL_RE.match(line)
    if not match:
        return False
    label = match.group(1)
    return not label.startswith(".")


def extract_comment(lines: List[str], label_index: int) -> str:
    comments: List[str] = []
    idx = label_index - 1
    while idx >= 0:
        line = lines[idx]
        if not COMMENT_RE.match(line):
            break
        text = line.lstrip(";").strip()
        if text:
            comments.append(text)
        idx -= 1
    comments.reverse()
    return " ".join(comments).strip()


def extract_code(lines: List[str], start: int, end: int) -> str:
    snippet = "\n".join(lines[start:end]).strip()
    return snippet


def extract_samples(path: Path, max_lines: int, min_comment_chars: int) -> Iterable[Sample]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []

    label_indices = [i for i, line in enumerate(lines) if is_label(line)]
    if not label_indices:
        return []

    samples: List[Sample] = []
    for idx, label_index in enumerate(label_indices):
        label_line = lines[label_index]
        match = LABEL_RE.match(label_line)
        if not match:
            continue
        label = match.group(1)
        comment = extract_comment(lines, label_index)
        if len(comment) < min_comment_chars:
            continue
        next_index = label_indices[idx + 1] if idx + 1 < len(label_indices) else len(lines)
        end_index = min(next_index, label_index + max_lines)
        code = extract_code(lines, label_index, end_index)
        if not code:
            continue
        samples.append(Sample(label=label, description=comment, code=code, source=str(path)))

    return samples


def generate_samples(paths: List[Path], max_lines: int, min_comment_chars: int) -> Iterable[Sample]:
    for root in paths:
        if root.is_file():
            if root.suffix.lower() == ".asm":
                yield from extract_samples(root, max_lines, min_comment_chars)
            continue
        for path in root.rglob("*.asm"):
            yield from extract_samples(path, max_lines, min_comment_chars)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--roots",
        nargs="+",
        type=Path,
        required=True,
        help="Roots to scan for ASM files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=80,
        help="Maximum lines of code per sample.",
    )
    parser.add_argument(
        "--min-comment-chars",
        type=int,
        default=12,
        help="Minimum length of comment description.",
    )
    args = parser.parse_args()

    samples = list(generate_samples(args.roots, args.max_lines, args.min_comment_chars))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as handle:
        for sample in samples:
            record = {
                "instruction": "Summarize what this 65816 routine does.",
                "input": f"```asm\n{sample.code}\n```",
                "output": sample.description,
                "domain": "asm-comment",
                "source": sample.source,
                "label": sample.label,
            }
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    print(f"Generated {len(samples)} samples -> {args.output}")


if __name__ == "__main__":
    main()
