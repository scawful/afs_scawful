#!/usr/bin/env python3
"""
Convert comment-based ASM samples into code-generation pairs.
"""
from __future__ import annotations

import argparse
import json
import random
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


def strip_code_fence(text: str) -> str:
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    if len(parts) < 2:
        return text.strip()
    return parts[1].replace("asm", "", 1).strip()


def build_instruction(description: str) -> str:
    description = description.strip().rstrip(".")
    if not description:
        return ""
    return f"Write a 65816 routine that {description}."


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
            description = record.get("output", "")
            instruction = build_instruction(description)
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
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
            count += 1
            if args.max_samples and count >= args.max_samples:
                break

    print(f"Generated {count} samples -> {args.output}")


if __name__ == "__main__":
    main()
