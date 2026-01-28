#!/usr/bin/env python3
"""
Validate ASM datasets using AsarValidatorV2 with semantic scoring.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from afs_scawful.training import TrainingSample
from afs_scawful.validators.asar_validator_v2 import AsarValidatorV2


@dataclass
class ValidationSummary:
    total: int = 0
    attempted: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


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


def build_sample(record: dict, force_domain: str | None) -> TrainingSample | None:
    if record.get("_parse_error"):
        return None
    output = record.get("output", "")
    if not output:
        return None
    if force_domain:
        cloned = dict(record)
        cloned["domain"] = force_domain
        return TrainingSample.from_dict(cloned)
    return TrainingSample.from_dict(record)


async def validate_samples(
    records: list[tuple[dict, TrainingSample]],
    validator: AsarValidatorV2,
    concurrency: int,
) -> tuple[ValidationSummary, list[dict], list[dict], dict, list[float], list[float]]:
    summary = ValidationSummary()
    error_categories = Counter()
    semantic_scores: list[float] = []
    semantic_scores_passed: list[float] = []
    passed_records: list[dict] = []
    failed_records: list[dict] = []

    semaphore = asyncio.Semaphore(concurrency)

    async def validate_single(record: dict, sample: TrainingSample):
        async with semaphore:
            if not validator.can_validate(sample):
                return record, None
            result = await validator.validate(sample)
            return record, result

    chunk_size = 250
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        tasks = [validate_single(record, sample) for record, sample in chunk]
        results = await asyncio.gather(*tasks)

        for record, result in results:
            summary.total += 1
            if result is None:
                summary.skipped += 1
                continue
            summary.attempted += 1
            if result.valid:
                summary.passed += 1
                passed_records.append(record)
            else:
                summary.failed += 1
                failed_records.append(record)

            if isinstance(result.details, dict):
                errors = result.details.get("errors", [])
                for error in errors:
                    category = error.get("category", "unknown")
                    error_categories[category] += 1
                semantic = result.details.get("semantic")
                if isinstance(semantic, dict):
                    score = semantic.get("score")
                    if isinstance(score, (int, float)):
                        semantic_scores.append(float(score))
                        if result.valid:
                            semantic_scores_passed.append(float(score))

    return summary, passed_records, failed_records, dict(error_categories), semantic_scores, semantic_scores_passed


def render_report(
    dataset_path: Path,
    summary: ValidationSummary,
    error_categories: dict,
    semantic_scores: list[float],
    semantic_scores_passed: list[float],
) -> dict:
    avg_semantic = sum(semantic_scores) / len(semantic_scores) if semantic_scores else 0.0
    avg_semantic_passed = (
        sum(semantic_scores_passed) / len(semantic_scores_passed)
        if semantic_scores_passed
        else 0.0
    )
    pass_rate = summary.passed / summary.attempted if summary.attempted else 0.0

    return {
        "dataset": str(dataset_path),
        "total": summary.total,
        "attempted": summary.attempted,
        "passed": summary.passed,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "pass_rate": round(pass_rate, 4),
        "error_categories": error_categories,
        "semantic": {
            "count": len(semantic_scores),
            "avg_score": round(avg_semantic, 4),
            "avg_score_passed": round(avg_semantic_passed, 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="JSONL dataset path.")
    parser.add_argument("--report", type=Path, required=True, help="Output JSON report path.")
    parser.add_argument("--passed", type=Path, help="Optional JSONL of passed records.")
    parser.add_argument("--failed", type=Path, help="Optional JSONL of failed records.")
    parser.add_argument("--concurrency", type=int, default=10, help="Async validation concurrency.")
    parser.add_argument("--rom-type", choices=["lorom", "hirom", "exlorom", "exhirom"], default="lorom")
    parser.add_argument("--no-semantic", action="store_true", help="Disable semantic scoring.")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit samples (0 = no limit).")
    parser.add_argument("--force-domain", type=str, default="", help="Override domain for validation.")
    args = parser.parse_args()

    dataset_path = args.input.expanduser().resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    validator = AsarValidatorV2(
        rom_type=args.rom_type,
        semantic_analysis=not args.no_semantic,
    )

    force_domain = args.force_domain.strip() or None
    records: list[tuple[dict, TrainingSample]] = []
    for record in iter_jsonl(dataset_path):
        sample = build_sample(record, force_domain)
        if not sample:
            continue
        records.append((record, sample))
        if args.max_samples and len(records) >= args.max_samples:
            break

    summary, passed_records, failed_records, error_categories, semantic_scores, semantic_scores_passed = asyncio.run(
        validate_samples(records, validator, args.concurrency)
    )

    report = render_report(
        dataset_path,
        summary,
        error_categories,
        semantic_scores,
        semantic_scores_passed,
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

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

    print(f"asar_v2_report: {args.report}")
    print(f"passed: {summary.passed} failed: {summary.failed} skipped: {summary.skipped}")


if __name__ == "__main__":
    main()
