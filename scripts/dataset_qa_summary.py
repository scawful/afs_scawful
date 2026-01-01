#!/usr/bin/env python3
"""
Summarize JSONL datasets with basic QA stats.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


REQUIRED_FIELDS = ("instruction", "output")


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"_parse_error": True}


def summarize_dataset(path: Path) -> dict:
    total = 0
    parse_errors = 0
    missing_fields = Counter()
    domain_counts = Counter()
    source_counts = Counter()
    input_chars = 0
    output_chars = 0
    instruction_chars = 0
    input_present = 0
    output_code_blocks = 0
    input_code_blocks = 0
    max_output_chars = 0
    max_input_chars = 0

    for record in iter_jsonl(path):
        total += 1
        if record.get("_parse_error"):
            parse_errors += 1
            continue

        for field in REQUIRED_FIELDS:
            if not record.get(field):
                missing_fields[field] += 1

        domain = record.get("domain", "").strip()
        if domain:
            domain_counts[domain] += 1

        source = record.get("source", "").strip()
        if source:
            source_counts[source] += 1

        instruction = record.get("instruction", "") or ""
        inp = record.get("input", "") or ""
        out = record.get("output", "") or ""

        instruction_chars += len(instruction)
        input_chars += len(inp)
        output_chars += len(out)
        if inp:
            input_present += 1
            max_input_chars = max(max_input_chars, len(inp))
            if "```" in inp:
                input_code_blocks += 1
        if out:
            max_output_chars = max(max_output_chars, len(out))
            if "```" in out:
                output_code_blocks += 1

    avg_instruction = instruction_chars / total if total else 0.0
    avg_input = input_chars / total if total else 0.0
    avg_output = output_chars / total if total else 0.0

    return {
        "path": str(path),
        "samples": total,
        "parse_errors": parse_errors,
        "missing_fields": dict(missing_fields),
        "domains": dict(domain_counts),
        "sources": dict(source_counts),
        "avg_instruction_chars": round(avg_instruction, 2),
        "avg_input_chars": round(avg_input, 2),
        "avg_output_chars": round(avg_output, 2),
        "input_present": input_present,
        "output_code_blocks": output_code_blocks,
        "input_code_blocks": input_code_blocks,
        "max_output_chars": max_output_chars,
        "max_input_chars": max_input_chars,
    }


def render_markdown(summaries: List[dict]) -> str:
    lines = [
        "# Dataset QA Summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]

    for summary in summaries:
        lines.append(f"## {summary['path']}")
        lines.append("")
        lines.append(f"- samples: {summary['samples']}")
        lines.append(f"- parse_errors: {summary['parse_errors']}")
        if summary["missing_fields"]:
            missing = ", ".join(f"{k}={v}" for k, v in summary["missing_fields"].items())
            lines.append(f"- missing_fields: {missing}")
        else:
            lines.append("- missing_fields: none")
        if summary["domains"]:
            domains = ", ".join(f"{k}={v}" for k, v in summary["domains"].items())
            lines.append(f"- domains: {domains}")
        if summary["sources"]:
            top_sources = list(summary["sources"].items())[:5]
            sources = ", ".join(f"{k}={v}" for k, v in top_sources)
            lines.append(f"- sources(top5): {sources}")
        lines.append(f"- avg_instruction_chars: {summary['avg_instruction_chars']}")
        lines.append(f"- avg_input_chars: {summary['avg_input_chars']}")
        lines.append(f"- avg_output_chars: {summary['avg_output_chars']}")
        lines.append(f"- input_present: {summary['input_present']}")
        lines.append(f"- input_code_blocks: {summary['input_code_blocks']}")
        lines.append(f"- output_code_blocks: {summary['output_code_blocks']}")
        lines.append(f"- max_input_chars: {summary['max_input_chars']}")
        lines.append(f"- max_output_chars: {summary['max_output_chars']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        required=True,
        help="JSONL dataset files to summarize.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output markdown path.",
    )
    args = parser.parse_args()

    summaries = [summarize_dataset(path) for path in args.inputs]
    markdown = render_markdown(summaries)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"Wrote summary -> {args.output}")


if __name__ == "__main__":
    main()
