#!/usr/bin/env python3
"""Build the ASAR-focused eval prompt pack (v1) from gold ASM data."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


CATEGORY_TARGETS = OrderedDict(
    [
        ("simple_routine", 10),
        ("dma_transfer", 8),
        ("sprite_code", 10),
        ("dungeon_mechanics", 8),
        ("hook_patch", 12),
        ("register_ops", 12),
    ]
)


EXPECTED_KEYWORDS = {
    "simple_routine": ["LDA", "STA", "RTS"],
    "dma_transfer": ["$4300", "$420B", "STA"],
    "sprite_code": ["PHB", "PHK", "PLB"],
    "dungeon_mechanics": ["CMP", "BNE", "RTL"],
    "hook_patch": ["org", "JSL", "RTL"],
    "register_ops": ["$2100", "$2105", "STA"],
}

CURATED_PROMPTS = {
    "simple_routine": [
        "Write a 65816 routine that copies 16 bytes from $7E2000 to $7E2100 using X as a countdown loop.",
        "Write a 65816 routine that clears a 256-byte buffer at $7E3000 and returns with RTS.",
        "Write a 65816 routine that compares $7E0F00 against #$0010 in 16-bit mode and sets carry when greater-or-equal.",
        "Write a 65816 routine that increments a frame counter at $7E1A00 and wraps it at #$003C.",
        "Write a 65816 routine that computes a checksum of 32 bytes at $7E2200 and stores it at $7E22FF.",
        "Write a 65816 routine that clamps A to the range #$00..#$3F and stores the result to $7E0040.",
        "Write a 65816 routine that toggles bit 0 of $7E0050 each call and returns.",
        "Write a 65816 routine that swaps two 16-bit values in $7E0100 and $7E0102.",
        "Write a 65816 routine that waits until $4210 VBlank flag is set, then returns.",
        "Write a 65816 routine that checks if Link HP at $7EF36D is zero and branches to a death handler label.",
    ],
    "dma_transfer": [
        "Write a 65816 routine that configures DMA channel 0 to copy 0x400 bytes from $7E4000 to VRAM $2000.",
        "Write a 65816 routine that performs a CGRAM DMA upload of 32 colors from $7E5000.",
        "Write a 65816 routine that sets $2116/$2117, streams 128 bytes to $2118/$2119, then exits.",
        "Write a 65816 routine that initializes HDMA channel 1 with table pointer at $7E6000.",
        "Write a 65816 routine that copies sprite tile data from ROM bank $1F to VRAM using DMA mode 1.",
        "Write a 65816 routine that uploads a 32x32 tilemap chunk to VRAM and updates the source pointer.",
        "Write a 65816 routine that performs two sequential DMA transfers: first graphics, then palette.",
        "Write a 65816 routine that disables interrupts around DMA setup and restores flags afterward.",
    ],
    "sprite_code": [
        "Write a 65816 sprite routine prologue with PHB/PHK/PLB, active check, state dispatch, and RTL epilogue.",
        "Write a 65816 routine that updates sprite X/Y velocity with acceleration and clamps max speed.",
        "Write a 65816 routine that checks sprite collision against player and applies knockback.",
        "Write a 65816 routine that advances sprite animation every 4 frames using a timer field.",
        "Write a 65816 routine that despawns a sprite when off-screen for 0x40 frames.",
        "Write a 65816 routine that spawns a projectile sprite in front of the parent sprite based on facing.",
        "Write a 65816 routine that toggles a sprite invulnerability flag after taking damage.",
        "Write a 65816 routine that performs OAM allocation and writes one 16x16 metasprite entry.",
        "Write a 65816 routine that runs a 3-state NPC AI: init, idle, talk.",
        "Write a 65816 routine that handles recoil motion by decaying velocity to zero.",
    ],
    "dungeon_mechanics": [
        "Write a 65816 routine that opens a key door when room kill count reaches zero.",
        "Write a 65816 routine that sets chest-open SRAM bit when a large chest is collected.",
        "Write a 65816 routine that toggles floor switch state and updates collision tiles.",
        "Write a 65816 routine that checks room ID and triggers a boss defeat cutscene for that room.",
        "Write a 65816 routine that validates dungeon key count before unlocking a shutter door.",
        "Write a 65816 routine that updates minecart track switch direction based on lever state.",
        "Write a 65816 routine that writes custom collision markers for water-fill rooms.",
        "Write a 65816 routine that warps player to a paired room when staircase flag is set.",
    ],
    "hook_patch": [
        "Write an Asar hook patch that uses org/pushpc/pullpc to intercept a vanilla routine and JSL to custom code.",
        "Write an Asar patch that installs a trampoline at $08BF0C and returns to original flow safely.",
        "Write a 65816 hook routine with register preservation that ends in RTL and can be called via JSL.",
        "Write an Asar patch that replaces a branch with JSL NewRoutine and pads remaining bytes with NOP.",
        "Write an Asar hook that checks a feature flag before running custom logic, then jumps back.",
        "Write an Asar patch that redirects a room-load routine to CustomRoomLoad and preserves A/X/Y.",
        "Write an Asar hook for a sprite update entrypoint that calls CustomSpriteTick then resumes vanilla.",
        "Write an Asar patch that injects a fast preflight check into a command handler path.",
        "Write an Asar patch that wraps custom code with PHB/PHK/PLB and restores bank before RTL.",
        "Write an Asar hook that installs at an absolute ROM address and documents instruction byte budget.",
        "Write an Asar patch that adds a JSL to telemetry code but keeps original carry/zero semantics.",
        "Write an Asar patch that inserts a one-time init guard using RAM flag and returns cleanly.",
    ],
    "register_ops": [
        "Write a 65816 routine that sets INIDISP ($2100) brightness to max and clears forced blank.",
        "Write a 65816 routine that configures BGMODE ($2105) for Mode 1 and 16x16 BG tile size.",
        "Write a 65816 routine that updates BG1HOFS/BG1VOFS from WRAM mirror values.",
        "Write a 65816 routine that configures CGWSEL/CGADSUB for half-color subtraction on BG1.",
        "Write a 65816 routine that writes fixed color data to COLDATA ($2132) for fade effect.",
        "Write a 65816 routine that enables NMI and joypad auto-read via $4200.",
        "Write a 65816 routine that sets up DMA registers $4300-$4307 for VRAM transfer.",
        "Write a 65816 routine that reads multiplication result from $4216/$4217 after writing operands.",
        "Write a 65816 routine that configures window mask registers $2123-$212B.",
        "Write a 65816 routine that enables main/sub screen layers via TM/TS ($212C/$212D).",
        "Write a 65816 routine that writes a palette entry to CGRAM using $2121/$2122.",
        "Write a 65816 routine that initializes Mode 7 matrix registers $211B-$2120.",
    ],
}


GENERATIVE_PREFIXES = (
    "write ",
    "create ",
    "implement ",
    "define ",
    "patch ",
    "generate ",
    "build ",
)

NON_GENERATIVE_PREFIXES = (
    "summarize ",
    "explain ",
    "describe ",
    "what does ",
    "what is ",
    "tell me ",
)


@dataclass(frozen=True)
class PromptCandidate:
    instruction: str
    score: float
    category: str


def _is_codegen_instruction(instruction: str) -> bool:
    lowered = instruction.strip().lower()
    if not lowered:
        return False
    if lowered.startswith(NON_GENERATIVE_PREFIXES):
        return False
    if lowered.startswith(GENERATIVE_PREFIXES):
        return True
    if "65816" in lowered and ("routine" in lowered or "assembly" in lowered):
        return True
    if "hook" in lowered or "patch" in lowered:
        return True
    return False


def _classify_instruction(instruction: str) -> str:
    lowered = instruction.lower()

    if any(k in lowered for k in ("dma", "hdma", "vram", "cgram", "$430", "$420b", "$2116", "$2122")):
        return "dma_transfer"

    if any(k in lowered for k in ("sprite", "ancilla", "oam", "npc", "projectile", "garnish", "boss", "enemy")):
        return "sprite_code"

    if any(k in lowered for k in ("dungeon", "room", "door", "chest", "switch", "warp", "stairs", "minecart")):
        return "dungeon_mechanics"

    if any(k in lowered for k in ("hook", "patch", "trampoline", "pushpc", "pullpc", "org ", "jsl", "jml")):
        return "hook_patch"

    if any(
        k in lowered
        for k in (
            "register",
            "inidisp",
            "bgmode",
            "ppu",
            "apu",
            "$21",
            "$42",
            "cgwsel",
            "cgadsub",
            "vblank",
        )
    ):
        return "register_ops"

    return "simple_routine"


def _normalize_instruction(instruction: str) -> str:
    collapsed = re.sub(r"\s+", " ", instruction.strip())
    return collapsed


def _iter_candidates(dataset_path: Path) -> list[PromptCandidate]:
    seen: set[str] = set()
    candidates: list[PromptCandidate] = []

    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            instruction = str(payload.get("instruction", "")).strip()
            if not _is_codegen_instruction(instruction):
                continue

            normalized = _normalize_instruction(instruction)
            if normalized in seen:
                continue
            seen.add(normalized)

            quality = payload.get("quality_score", 0.0)
            try:
                score = float(quality)
            except (TypeError, ValueError):
                score = 0.0

            candidates.append(
                PromptCandidate(
                    instruction=normalized,
                    score=score,
                    category=_classify_instruction(normalized),
                )
            )

    return candidates


def _select_prompt_pack(candidates: list[PromptCandidate], seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_category: dict[str, list[PromptCandidate]] = {k: [] for k in CATEGORY_TARGETS}

    for candidate in candidates:
        by_category.setdefault(candidate.category, []).append(candidate)

    for bucket in by_category.values():
        bucket.sort(key=lambda item: (item.score, len(item.instruction)), reverse=True)

    used_instructions: set[str] = set()
    output: list[dict] = []

    def pop_next(cat: str) -> PromptCandidate | None:
        bucket = by_category.get(cat, [])
        while bucket:
            candidate = bucket.pop(0)
            if candidate.instruction in used_instructions:
                continue
            used_instructions.add(candidate.instruction)
            return candidate
        return None

    fallback_pool = sorted(candidates, key=lambda item: (item.score, len(item.instruction)), reverse=True)
    rng.shuffle(fallback_pool)

    for category, needed in CATEGORY_TARGETS.items():
        for curated in CURATED_PROMPTS.get(category, []):
            if len([row for row in output if row["category"] == category]) >= needed:
                break
            if curated in used_instructions:
                continue
            used_instructions.add(curated)
            output.append(
                {
                    "instruction": curated,
                    "input": "Output only 65816 assembly.",
                    "category": category,
                    "expected_keywords": EXPECTED_KEYWORDS[category],
                }
            )

        selected: list[PromptCandidate] = []
        already = len([row for row in output if row["category"] == category])
        needed_remaining = max(0, needed - already)

        while len(selected) < needed_remaining:
            next_item = pop_next(category)
            if next_item is None:
                break
            selected.append(next_item)

        if len(selected) < needed_remaining:
            for candidate in fallback_pool:
                if candidate.instruction in used_instructions:
                    continue
                used_instructions.add(candidate.instruction)
                selected.append(candidate)
                if len(selected) == needed_remaining:
                    break

        for candidate in selected:
            output.append(
                {
                    "instruction": candidate.instruction,
                    "input": "Output only 65816 assembly.",
                    "category": category,
                    "expected_keywords": EXPECTED_KEYWORDS[category],
                }
            )

    return output


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build docs/eval/asar_eval_v1.jsonl.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path.home() / "src" / "training" / "datasets" / "sources" / "asm_gold_asar_pass_20260102.jsonl",
        help="Input JSONL with instruction/output samples.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "src" / "lab" / "afs-scawful" / "docs" / "eval" / "asar_eval_v1.jsonl",
        help="Output prompt pack JSONL path.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic selection seed.")
    args = parser.parse_args()

    dataset_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    candidates = _iter_candidates(dataset_path)
    if not candidates:
        print("warning: no code-generation candidates found, using curated prompts only")

    rows = _select_prompt_pack(candidates, seed=args.seed)
    _write_jsonl(output_path, rows)

    by_category: dict[str, int] = {k: 0 for k in CATEGORY_TARGETS}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1

    print(f"asar_eval_pack: {output_path}")
    print(f"total_prompts: {len(rows)}")
    for category, count in by_category.items():
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
