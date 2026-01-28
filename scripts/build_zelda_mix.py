#!/usr/bin/env python3
"""Build the Zelda 16B training mix (train/eval JSONL)."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DatasetSource:
    name: str
    filename: str


DEFAULT_DATASETS = [
    DatasetSource("vultr_train_full", "vultr_train_full.jsonl"),
    DatasetSource("vultr_gold_full", "vultr_gold_full.jsonl"),
    DatasetSource("oos_enriched_v1_normalized_notodo", "oos_enriched_v1_normalized_notodo.jsonl"),
    DatasetSource("asm_gold_asar_pass_20260102", "asm_gold_asar_pass_20260102.jsonl"),
    DatasetSource("nerv_watcher_v1", "nerv_watcher_v1.jsonl"),
    DatasetSource("expert_router_v1", "expert_router_v1.jsonl"),
]


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


def load_records(path: Path) -> tuple[list[dict], int]:
    records = []
    parse_errors = 0
    for record in iter_jsonl(path):
        if record.get("_parse_error"):
            parse_errors += 1
            continue
        records.append(record)
    return records, parse_errors


def split_records(
    records: list[dict],
    rng: random.Random,
    eval_fraction: float,
    min_eval_samples: int,
) -> tuple[list[dict], list[dict]]:
    if not records:
        return [], []
    rng.shuffle(records)
    eval_count = int(round(len(records) * eval_fraction))
    if eval_count < min_eval_samples:
        eval_count = min_eval_samples
    if eval_count > len(records):
        eval_count = len(records)
    eval_records = records[:eval_count]
    train_records = records[eval_count:]
    return train_records, eval_records


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Zelda 16B mix dataset.")
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=Path.home() / "src" / "training" / "datasets",
        help="Root directory for source datasets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "src" / "training" / "datasets" / "zelda_16b_mix_v1",
        help="Output directory for train/eval JSONL.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed.")
    parser.add_argument(
        "--eval-fraction",
        type=float,
        default=0.02,
        help="Fraction of each dataset reserved for eval.",
    )
    parser.add_argument(
        "--min-eval-samples",
        type=int,
        default=1,
        help="Minimum eval samples per dataset.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output directory.",
    )
    args = parser.parse_args()

    datasets_root = args.datasets_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if any(output_dir.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output directory not empty: {output_dir} (use --overwrite)")

    rng = random.Random(args.seed)
    train_records: list[dict] = []
    eval_records: list[dict] = []
    dataset_stats = []
    parse_errors_total = 0

    for dataset in DEFAULT_DATASETS:
        path = datasets_root / dataset.filename
        if not path.exists():
            raise SystemExit(f"Dataset not found: {path}")

        records, parse_errors = load_records(path)
        parse_errors_total += parse_errors
        train_split, eval_split = split_records(
            records,
            rng,
            eval_fraction=args.eval_fraction,
            min_eval_samples=args.min_eval_samples,
        )
        train_records.extend(train_split)
        eval_records.extend(eval_split)
        dataset_stats.append(
            {
                "name": dataset.name,
                "path": str(path),
                "total": len(records),
                "train": len(train_split),
                "eval": len(eval_split),
                "parse_errors": parse_errors,
            }
        )

    rng.shuffle(train_records)
    rng.shuffle(eval_records)

    train_path = output_dir / "train.jsonl"
    eval_path = output_dir / "eval.jsonl"
    val_path = output_dir / "val.jsonl"
    write_jsonl(train_path, train_records)
    write_jsonl(eval_path, eval_records)
    write_jsonl(val_path, eval_records)

    total_train = len(train_records)
    total_eval = len(eval_records)
    total_all = total_train + total_eval

    for entry in dataset_stats:
        entry["ratio_percent"] = round((entry["total"] / total_all) * 100, 2) if total_all else 0.0

    metadata = {
        "name": "zelda_16b_mix_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "seed": args.seed,
        "eval_fraction": args.eval_fraction,
        "min_eval_samples": args.min_eval_samples,
        "datasets_root": str(datasets_root),
        "datasets": dataset_stats,
        "total_train": total_train,
        "total_eval": total_eval,
        "total_records": total_all,
        "parse_errors_total": parse_errors_total,
        "outputs": {
            "train": str(train_path),
            "eval": str(eval_path),
            "val": str(val_path),
        },
        "notes": [
            "train.jsonl and eval.jsonl are shuffled.",
            "val.jsonl mirrors eval.jsonl for training convenience.",
        ],
    }

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"train.jsonl: {train_path}")
    print(f"eval.jsonl: {eval_path}")
    print(f"metadata.json: {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
