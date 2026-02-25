#!/usr/bin/env python3
"""Build distill_prompts_v1.jsonl from ASAR and z3dk sources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_INPUT_TEXT = "Output only 65816 assembly."

CATEGORY_KEYWORDS = {
    "simple_routine": ["LDA", "STA", "RTS"],
    "dma_transfer": ["$4300", "$420B", "STA"],
    "sprite_code": ["PHB", "PHK", "PLB"],
    "dungeon_mechanics": ["CMP", "BNE", "RTL"],
    "hook_patch": ["org", "JSL", "RTL"],
    "register_ops": ["$2100", "$2105", "STA"],
    "scaffold_completion": ["PHB", "RTS", "RTL"],
}

GENERATOR_CATEGORY = {
    "build_hook_writing": "hook_patch",
    "build_scaffold_completion": "scaffold_completion",
    "build_static_analysis": "simple_routine",
}


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _resolve_expected_keywords(category: str) -> list[str]:
    return CATEGORY_KEYWORDS.get(category, ["LDA", "STA", "RTS"])


def _infer_category(sample: dict) -> str:
    metadata = sample.get("_metadata", {}) or {}
    generator = metadata.get("generator", "")
    if generator in GENERATOR_CATEGORY:
        return GENERATOR_CATEGORY[generator]

    if sample.get("domain") == "asm":
        return "simple_routine"
    return "register_ops"


def _add_prompt(
    out: list[dict],
    seen: set[str],
    instruction: str,
    category: str,
) -> bool:
    normalized = _normalize(instruction)
    if not normalized or normalized in seen:
        return False
    seen.add(normalized)
    out.append(
        {
            "instruction": normalized,
            "input": DEFAULT_INPUT_TEXT,
            "category": category,
            "expected_keywords": _resolve_expected_keywords(category),
        }
    )
    return True


def _augment_prompts(count: int) -> list[tuple[str, str]]:
    prompts: list[tuple[str, str]] = []

    for idx in range(count):
        if idx % 4 == 0:
            prompts.append(
                (
                    (
                        f"Write an asar hook patch that installs at ${0x088000 + idx * 8:06X}, "
                        "preserves A/X/Y, calls a custom subroutine with JSL, and returns via RTL."
                    ),
                    "hook_patch",
                )
            )
        elif idx % 4 == 1:
            prompts.append(
                (
                    (
                        f"Write a sprite state routine for sprite slot {idx % 16} with init/active/cooldown "
                        "states, PHB/PHK/PLB prologue, and safe register restore."
                    ),
                    "sprite_code",
                )
            )
        elif idx % 4 == 2:
            prompts.append(
                (
                    (
                        f"Write a DMA routine to transfer {0x80 + (idx % 8) * 0x20} bytes from $7E{0x4000 + idx * 16:04X} "
                        "to VRAM using channel 0 and trigger with $420B."
                    ),
                    "dma_transfer",
                )
            )
        else:
            prompts.append(
                (
                    (
                        f"Write a 65816 routine that configures INIDISP, BGMODE, and BG1 scroll registers for "
                        f"room setup variant {idx}."
                    ),
                    "register_ops",
                )
            )
    return prompts


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description="Build distillation prompt pack.")
    parser.add_argument(
        "--asar-prompts",
        type=Path,
        default=repo_root / "docs" / "eval" / "asar_eval_v1.jsonl",
        help="ASAR eval prompt pack source.",
    )
    parser.add_argument(
        "--z3dk-dataset",
        type=Path,
        default=Path.home() / "src" / "training" / "datasets" / "z3dk" / "z3dk_training_v1.jsonl",
        help="z3dk training dataset source.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "docs" / "eval" / "distill_prompts_v1.jsonl",
        help="Output prompt pack path.",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=240,
        help="Target number of prompt rows (default: 240).",
    )
    parser.add_argument(
        "--augment-count",
        type=int,
        default=60,
        help="Number of synthetic augment prompts to inject (default: 60).",
    )
    args = parser.parse_args()

    asar_prompts = _load_jsonl(args.asar_prompts.expanduser().resolve())
    z3dk_rows = _load_jsonl(args.z3dk_dataset.expanduser().resolve())

    output: list[dict] = []
    seen: set[str] = set()

    # 1) Keep the full ASAR eval pack.
    for row in asar_prompts:
        _add_prompt(
            output,
            seen,
            str(row.get("instruction", "")),
            str(row.get("category", "simple_routine")),
        )

    # 2) Pull code-centric z3dk prompts (domain=asm first).
    asm_rows = [row for row in z3dk_rows if row.get("domain") == "asm"]
    for row in asm_rows:
        if len(output) >= args.target_count:
            break
        _add_prompt(output, seen, str(row.get("instruction", "")), _infer_category(row))

    # 3) Add synthetic prompts from augmentation templates.
    for instruction, category in _augment_prompts(args.augment_count):
        if len(output) >= args.target_count:
            break
        _add_prompt(output, seen, instruction, category)

    # 4) Fill with remaining z3dk rows if needed.
    if len(output) < args.target_count:
        for row in z3dk_rows:
            if len(output) >= args.target_count:
                break
            _add_prompt(output, seen, str(row.get("instruction", "")), _infer_category(row))

    output_path = args.output.expanduser().resolve()
    _write_jsonl(output_path, output)

    print(f"asar_prompts: {args.asar_prompts.expanduser().resolve()}")
    print(f"z3dk_dataset: {args.z3dk_dataset.expanduser().resolve()}")
    print(f"output: {output_path}")
    print(f"total_prompts: {len(output)}")


if __name__ == "__main__":
    main()
