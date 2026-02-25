#!/usr/bin/env python3
"""
Convert AFS training datasets to MLX chat format for LoRA fine-tuning.

Converts JSONL instruction/output format -> MLX messages format with
model-specific system prompts, train/valid/test splits.

Usage:
    python scripts/convert_datasets_to_mlx.py \
        --target agahnim \
        --input ~/src/training/datasets/z3dk/z3dk_training_v1.jsonl \
        --output-dir ~/src/training/datasets/zelda/mlx_data_agahnim/

    python scripts/convert_datasets_to_mlx.py \
        --target nayru \
        --input ~/src/training/datasets/iquest_40b_unified_v3/train.jsonl \
        --extra ~/src/training/datasets/z3dk/z3dk_training_v1.jsonl \
        --extra ~/src/training/datasets/zelda/distill_cloud_v1.jsonl \
        --output-dir ~/src/training/datasets/zelda/mlx_data_nayru/
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SEED = 42

# Model-specific system prompts
SYSTEM_PROMPTS = {
    "agahnim": (
        "You are Agahnim, a 65816 build and integration expert using asar. "
        "You specialize in writing asar patches, hooks (pushpc/pullpc/org), "
        "JSL trampolines, namespace bridging, scaffold completion, and SNES "
        "hardware register configuration. Output clean, valid 65816 assembly "
        "with asar-compatible syntax. Include comments for clarity."
    ),
    "nayru": (
        "You are Nayru, the Oracle of Ages and embodiment of Wisdom. "
        "You specialize in explaining complex SNES systems, writing "
        "documentation, teaching 65816 assembly concepts, analyzing code "
        "for bugs, and describing hardware behavior. Be thorough, patient, "
        "and precise in your explanations. When code is requested, output "
        "valid 65816 assembly with detailed comments."
    ),
}

# Category filters per target model
TARGET_CATEGORIES = {
    "agahnim": {
        "include": [
            "hook_writing", "hook_patch", "scaffold_completion",
            "register_ops", "dma_transfer", "simple_routine",
            "opcode_qa",  # subset: addressing modes / opcodes
        ],
        "exclude_patterns": [
            "explain", "describe", "what does", "what is", "why",
            "documentation", "teach",
        ],
    },
    "nayru": {
        "include": [
            "opcode_qa", "register_qa", "quirks_qa",
            "static_analysis", "explanation", "memory_qa",
            "documentation", "code_explanation",
        ],
        "exclude_patterns": [],
    },
}


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file, returning list of dicts."""
    samples = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            samples.append(json.loads(line))
    return samples


def to_mlx_chat(sample: dict, system_prompt: str) -> dict:
    """Convert instruction/output sample to MLX chat format."""
    instruction = sample.get("instruction", "")
    inp = sample.get("input", "")
    output = sample.get("output", "")

    user_content = instruction
    if inp:
        user_content = f"{instruction}\n\n{inp}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": output},
    ]
    return {"messages": messages}


def filter_for_target(
    samples: list[dict],
    target: str,
) -> list[dict]:
    """Filter samples based on target model category preferences."""
    config = TARGET_CATEGORIES.get(target)
    if not config:
        return samples

    include_cats = set(config.get("include", []))
    exclude_patterns = config.get("exclude_patterns", [])

    filtered = []
    for sample in samples:
        # Check category
        cat = (
            sample.get("_metadata", {}).get("z3dk_category", "")
            or sample.get("_metadata", {}).get("category", "")
            or sample.get("category", "")
            or ""
        )

        # If we have include categories and the sample has a category, filter
        if include_cats and cat and cat not in include_cats:
            continue

        # Check exclude patterns in instruction
        instruction = sample.get("instruction", "").lower()
        if exclude_patterns:
            skip = False
            for pattern in exclude_patterns:
                if pattern in instruction:
                    skip = True
                    break
            if skip:
                continue

        filtered.append(sample)

    return filtered


def create_splits(
    samples: list[dict],
    val_ratio: float = 0.1,
    test_size: int = 10,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split samples into train/valid/test."""
    rng = random.Random(SEED)
    shuffled = samples[:]
    rng.shuffle(shuffled)

    val_size = max(int(len(shuffled) * val_ratio), 1)
    test_samples = shuffled[:test_size]
    val_samples = shuffled[test_size:test_size + val_size]
    train_samples = shuffled[test_size + val_size:]

    return train_samples, val_samples, test_samples


def write_jsonl(samples: list[dict], path: Path):
    """Write samples to JSONL file."""
    with open(path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Convert AFS datasets to MLX chat format."
    )
    parser.add_argument(
        "--target", "-t", required=True,
        choices=list(SYSTEM_PROMPTS.keys()),
        help="Target model (agahnim, nayru).",
    )
    parser.add_argument(
        "--input", "-i", required=True, action="append",
        help="Input JSONL file(s). Can specify multiple.",
    )
    parser.add_argument(
        "--extra", "-e", action="append", default=[],
        help="Additional JSONL files to merge.",
    )
    parser.add_argument(
        "--output-dir", "-o", required=True,
        help="Output directory for MLX data (train.jsonl, valid.jsonl, test.jsonl).",
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.1,
        help="Validation split ratio (default: 0.1).",
    )
    parser.add_argument(
        "--no-filter", action="store_true",
        help="Skip category filtering.",
    )
    args = parser.parse_args()

    system_prompt = SYSTEM_PROMPTS[args.target]
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all input files
    all_samples = []
    input_files = args.input + args.extra
    for input_path in input_files:
        path = Path(input_path).expanduser().resolve()
        if not path.exists():
            print(f"Warning: {path} not found, skipping")
            continue
        samples = load_jsonl(path)
        print(f"Loaded {len(samples)} samples from {path.name}")
        all_samples.extend(samples)

    print(f"Total raw samples: {len(all_samples)}")

    # Filter for target
    if not args.no_filter:
        filtered = filter_for_target(all_samples, args.target)
        print(f"After filtering for {args.target}: {len(filtered)} samples")
    else:
        filtered = all_samples

    # Convert to MLX chat format
    mlx_samples = [to_mlx_chat(s, system_prompt) for s in filtered]

    # Split
    train, valid, test = create_splits(
        mlx_samples, val_ratio=args.val_ratio,
    )

    # Write
    write_jsonl(train, output_dir / "train.jsonl")
    write_jsonl(valid, output_dir / "valid.jsonl")
    write_jsonl(test, output_dir / "test.jsonl")

    print(f"\n{'='*60}")
    print(f"MLX Dataset: {args.target}")
    print(f"{'='*60}")
    print(f"Train: {len(train)} samples -> {output_dir / 'train.jsonl'}")
    print(f"Valid: {len(valid)} samples -> {output_dir / 'valid.jsonl'}")
    print(f"Test:  {len(test)} samples -> {output_dir / 'test.jsonl'}")
    print(f"\nReady for: mlx_lm.lora --data {output_dir}")


if __name__ == "__main__":
    main()
