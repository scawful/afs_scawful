#!/usr/bin/env python3
"""
Validate ASM code outputs in JSONL datasets using Asar/ASM validators.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from afs_scawful.training import TrainingSample
from afs_scawful.validators import AsarValidator, AsmValidator


@dataclass
class ValidationSummary:
    total: int = 0
    attempted: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


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


def build_sample(record: dict, field: str) -> TrainingSample | None:
    if record.get("_parse_error"):
        return None
    code = record.get(field, "")
    if not code:
        return None
    return TrainingSample(
        instruction=record.get("instruction", ""),
        input=record.get("input", ""),
        output=code,
        domain=record.get("domain", "asm"),
        source=record.get("source", ""),
        metadata=record.get("metadata", {}) or {},
    )


async def validate_samples(
    samples: List[tuple[dict, TrainingSample]],
    use_asar: bool,
    use_asm: bool,
    concurrency: int = 15
) -> tuple[ValidationSummary, list[dict], list[dict]]:
    summary = ValidationSummary()
    passed_records: list[dict] = []
    failed_records: list[dict] = []

    validators = []
    if use_asar:
        validators.append(AsarValidator())
    if use_asm:
        validators.append(AsmValidator())

    semaphore = asyncio.Semaphore(concurrency)

    async def validate_single(record, sample):
        async with semaphore:
            ok = True
            for validator in validators:
                result = await validator.validate(sample)
                if not result.valid:
                    ok = False
                    break
            return record, ok

    # Process in chunks to avoid memory/file descriptor issues
    chunk_size = 500
    for i in range(0, len(samples), chunk_size):
        chunk = samples[i:i + chunk_size]
        print(f"Processing chunk {i//chunk_size + 1} ({i} to {min(i+chunk_size, len(samples))})...")
        tasks = [validate_single(record, sample) for record, sample in chunk]
        results = await asyncio.gather(*tasks)

        for record, ok in results:
            summary.total += 1
            summary.attempted += 1
            if ok:
                summary.passed += 1
                passed_records.append(record)
            else:
                summary.failed += 1
                failed_records.append(record)

    return summary, passed_records, failed_records


def render_markdown(path: Path, field: str, summary: ValidationSummary) -> str:
    lines = [
        "# ASM Dataset Validation",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Dataset: {path}",
        f"Field: {field}",
        "",
        f"- total_records: {summary.total}",
        f"- attempted: {summary.attempted}",
        f"- passed: {summary.passed}",
        f"- failed: {summary.failed}",
        f"- skipped: {summary.skipped}",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="JSONL dataset path.")
    parser.add_argument("--field", default="output", help="Field to validate (default: output).")
    parser.add_argument("--asar", action="store_true", help="Use Asar validator.")
    parser.add_argument("--asm", action="store_true", help="Use ASM static validator.")
    parser.add_argument("--report", type=Path, required=True, help="Output markdown report.")
    parser.add_argument("--passed", type=Path, help="Optional JSONL of passed records.")
    parser.add_argument("--failed", type=Path, help="Optional JSONL of failed records.")
    args = parser.parse_args()

    use_asar = args.asar or not args.asm
    use_asm = args.asm

    records: list[tuple[dict, TrainingSample]] = []
    summary = ValidationSummary()
    for record in iter_jsonl(args.input):
        summary.total += 1
        sample = build_sample(record, args.field)
        if not sample:
            summary.skipped += 1
            continue
        records.append((record, sample))

    summary.attempted = len(records)
    results, passed_records, failed_records = asyncio.run(
        validate_samples(records, use_asar=use_asar, use_asm=use_asm)
    )
    results.total = summary.total
    results.skipped = summary.skipped

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(args.input, args.field, results), encoding="utf-8")
    if args.passed:
        args.passed.parent.mkdir(parents=True, exist_ok=True)
        with args.passed.open("w", encoding="utf-8") as handle:
            for record in passed_records:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    if args.failed:
        args.failed.parent.mkdir(parents=True, exist_ok=True)
        with args.failed.open("w", encoding="utf-8") as handle:
            for record in failed_records:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    print(f"validation_report: {args.report}")
    print(f"passed: {len(passed_records)} failed: {len(failed_records)} skipped: {summary.skipped}")


if __name__ == "__main__":
    main()
