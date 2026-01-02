#!/usr/bin/env python3
"""
Generate label-free fixup samples from eval failure JSONL.

Replaces undefined labels with numeric addresses to reduce Asar label errors.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


LABEL_ERROR_RE = re.compile(r"Label '([^']+)' wasn't found")
TOKEN_BOUNDARY = re.compile(r"[A-Za-z0-9_]")


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


def parse_missing_labels(error_text: str) -> list[str]:
    return sorted(set(LABEL_ERROR_RE.findall(error_text)))


def build_label_map(labels: list[str], base_short: int, base_long: int, step: int) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    for idx, label in enumerate(labels):
        short_addr = base_short + idx * step
        long_addr = base_long + idx * step
        mapping[label] = {
            "short": f"${short_addr:04X}",
            "long": f"${long_addr:06X}",
        }
    return mapping


def is_long_context(line: str) -> bool:
    upper = line.upper()
    if ".L" in upper:
        return True
    if "JSL" in upper or "JML" in upper:
        return True
    if ">>16" in upper or ">> 16" in upper:
        return True
    return False


def replace_labels_in_line(line: str, label_map: dict[str, dict[str, str]]) -> str:
    if not label_map:
        return line
    code, sep, comment = line.partition(";")
    use_long = is_long_context(code)
    replaced = code
    for label, addrs in label_map.items():
        addr = addrs["long"] if use_long else addrs["short"]
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])")
        replaced = pattern.sub(addr, replaced)
    if sep:
        return f"{replaced}{sep}{comment}"
    return replaced


def replace_labels(code: str, label_map: dict[str, dict[str, str]]) -> str:
    return "\n".join(
        replace_labels_in_line(line, label_map) for line in code.splitlines()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build label-free fixups from eval failures.")
    parser.add_argument("--input", type=Path, required=True, help="Eval failures JSONL path.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument("--rejected", type=Path, help="Rejected JSONL path.")
    parser.add_argument("--report", type=Path, help="Optional JSON report path.")
    parser.add_argument("--base-short", type=lambda x: int(x, 0), default="0x2000")
    parser.add_argument("--base-long", type=lambda x: int(x, 0), default="0x7E2000")
    parser.add_argument("--step", type=lambda x: int(x, 0), default="0x2")
    parser.add_argument("--require-label-errors", action="store_true", help="Only keep label_not_found failures.")
    args = parser.parse_args()

    stats = Counter()
    rejected = []

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.rejected:
        args.rejected.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as out_handle:
        for record in iter_jsonl(args.input):
            stats["total"] += 1
            if record.get("_parse_error"):
                stats["parse_error"] += 1
                if args.rejected:
                    rejected.append(record)
                continue

            errors = record.get("_metadata", {}).get("errors", "")
            labels = parse_missing_labels(errors)
            if args.require_label_errors and not labels:
                stats["reject_no_labels"] += 1
                if args.rejected:
                    rejected.append(record)
                continue

            output = record.get("output", "")
            label_map = build_label_map(labels, args.base_short, args.base_long, args.step)
            rewritten = replace_labels(output, label_map)

            if rewritten == output:
                stats["unchanged"] += 1
            else:
                stats["rewritten"] += 1

            metadata = record.get("_metadata", {}) if isinstance(record.get("_metadata"), dict) else {}
            metadata.update({
                "label_free": True,
                "label_replacement_count": len(labels),
                "label_replacements": label_map,
                "label_replacement_strategy": "heuristic",
            })

            payload = {
                "instruction": record.get("instruction", ""),
                "input": record.get("input", ""),
                "output": rewritten,
                "domain": "asm-eval-fixup",
                "source": f"{record.get('source', '')}:label_free",
                "_metadata": metadata,
            }
            out_handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
            stats["kept"] += 1

    if args.rejected:
        with args.rejected.open("w", encoding="utf-8") as rej_handle:
            for record in rejected:
                rej_handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    if args.report:
        report = {
            "input": str(args.input),
            "output": str(args.output),
            "rejected": str(args.rejected) if args.rejected else None,
            "stats": dict(stats),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"label_free: {stats.get('kept', 0)} / {stats['total']} -> {args.output}")
    if args.rejected:
        print(f"rejected: {len(rejected)} -> {args.rejected}")


if __name__ == "__main__":
    main()
