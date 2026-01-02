#!/usr/bin/env python3
"""
Convert comment-based ASM samples into code-generation pairs.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Iterable


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


_FILE_MARKER_PATTERNS = [
    r";\s*\*?\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP\s*LOCATION|ALTERNATE\s*ENTRY\s*POINT|DATA|MAIN\s*ENTRY\s*POINT)?\.?",
    r"\*\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP\s*LOCATION|ALTERNATE\s*ENTRY\s*POINT|DATA|MAIN\s*ENTRY\s*POINT)?\.?",
    r"={4,}",
    r"-{4,}",
    r";\s*TODO\s*$",
    r";\s*\$[0-9A-Fa-f]+\s*$",
]
_file_marker_regexes = [re.compile(p, re.IGNORECASE) for p in _FILE_MARKER_PATTERNS]
_org_regex = re.compile(r"\borg\s+\$[0-9A-Fa-f]+\b", re.IGNORECASE)


def strip_code_fence(text: str) -> str:
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    if len(parts) < 2:
        return text.strip()
    cleaned = parts[1].strip()
    if cleaned.lower().startswith("asm"):
        cleaned = cleaned[3:].strip()
    return cleaned


def clean_description(text: str) -> tuple[str, bool]:
    original = text
    cleaned = text
    for pattern in _file_marker_regexes:
        cleaned = pattern.sub("", cleaned)
    cleaned = _org_regex.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[\s,;:]+$", "", cleaned).strip()
    return cleaned, cleaned != original


def build_instruction(description: str) -> tuple[str, bool]:
    description, was_cleaned = clean_description(description)
    description = description.strip().rstrip(".")
    if len(description) < 8 or not re.search(r"[A-Za-z]", description):
        return "", was_cleaned
    return f"Write a 65816 routine that {description}.", was_cleaned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL dataset.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL dataset.")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit output samples (0 = no limit).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling.")
    parser.add_argument("--sample-rate", type=float, default=1.0, help="Probability to keep each sample.")
    args = parser.parse_args()

    random.seed(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with args.output.open("w", encoding="utf-8") as handle:
        for record in iter_jsonl(args.input):
            if args.sample_rate < 1.0 and random.random() > args.sample_rate:
                continue
            raw_description = record.get("output", "")
            instruction, was_cleaned = build_instruction(raw_description)
            if not instruction:
                continue
            code = strip_code_fence(record.get("input", ""))
            if not code:
                continue
            payload = {
                "instruction": instruction,
                "input": "",
                "output": code,
                "domain": "asm-generate",
                "source": record.get("source", ""),
                "metadata": {
                    "label": record.get("label", ""),
                    "origin_domain": record.get("domain", ""),
                    "description_cleaned": was_cleaned,
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
            count += 1
            if args.max_samples and count >= args.max_samples:
                break

    print(f"Generated {count} samples -> {args.output}")


if __name__ == "__main__":
    main()
