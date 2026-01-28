#!/usr/bin/env python3
"""
Build a de-duplicated gold dataset from multiple JSONL inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"_parse_error": True}


def record_key(record: dict) -> str:
    instruction = (record.get("instruction") or "").strip()
    inp = (record.get("input") or "").strip()
    output = (record.get("output") or "").strip()
    payload = "\n".join([instruction, inp, output])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gold dataset from JSONL inputs.")
    parser.add_argument("--inputs", nargs="+", type=Path, required=True, help="Input JSONL datasets.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument("--report", type=Path, help="Optional JSON report path.")
    parser.add_argument("--tag", type=str, default="", help="Gold tag for metadata.")
    args = parser.parse_args()

    stats = Counter()
    domain_counts = Counter()
    source_counts = Counter()
    seen = set()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    tag = args.tag or args.output.stem

    with args.output.open("w", encoding="utf-8") as out_handle:
        for input_path in args.inputs:
            input_name = input_path.name
            for record in iter_jsonl(input_path):
                stats["total"] += 1
                if record.get("_parse_error"):
                    stats["parse_error"] += 1
                    continue

                instruction = (record.get("instruction") or "").strip()
                output = (record.get("output") or "").strip()
                if not instruction or not output:
                    stats["missing_fields"] += 1
                    continue

                key = record_key(record)
                if key in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(key)

                metadata = record.get("_metadata") if isinstance(record.get("_metadata"), dict) else {}
                metadata.update({
                    "gold_source": input_name,
                    "gold_tag": tag,
                })

                payload = dict(record)
                payload.setdefault("input", "")
                payload.setdefault("domain", "asm")
                payload.setdefault("source", input_name)
                payload["_metadata"] = metadata

                domain_counts[payload["domain"]] += 1
                source_counts[payload["source"]] += 1

                out_handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
                stats["kept"] += 1

    stats["dropped"] = stats["total"] - stats["kept"]

    if args.report:
        report = {
            "inputs": [str(p) for p in args.inputs],
            "output": str(args.output),
            "stats": dict(stats),
            "domains": dict(domain_counts),
            "sources": dict(source_counts),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"gold_dataset: {stats['kept']} / {stats['total']} -> {args.output}")


if __name__ == "__main__":
    main()
