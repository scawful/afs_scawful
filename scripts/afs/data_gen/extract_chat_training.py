#!/usr/bin/env python3
"""Extract high-quality training samples from chat logs.

Filters for:
1. Assembly/65816 related content
2. Oracle of Secrets discussions
3. Debugging/problem solving
4. High quality scores
"""

import json
from pathlib import Path
from datetime import datetime
import re

DATASETS_DIR = Path.home() / "src/training/datasets"
OUTPUT_DIR = Path.home() / ".context/training_pools"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Keywords for different categories
ASM_KEYWORDS = [
    "65816", "assembly", "asm", "sprite", "snes", "dma", "vram", "oam",
    "sta", "lda", "jsr", "jsl", "rts", "rtl", "rep", "sep", "branch",
    "register", "bank", "address", "opcode", "instruction"
]

OOS_KEYWORDS = [
    "oracle", "secrets", "alttp", "zelda", "link", "overworld", "dungeon",
    "zsow", "zscream", "asar", "rom hack", "romhack", "sprite", "npc",
    "boss", "mask", "ocarina", "time system", "menu"
]

DEBUG_KEYWORDS = [
    "fix", "bug", "debug", "crash", "issue", "error", "problem", "wrong",
    "broken", "regression", "stack", "corrupt", "overflow", "underflow"
]

QUALITY_THRESHOLD = 0.7

def matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any keywords."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)

def extract_samples(jsonl_path: Path, domain: str) -> tuple[list, list, list]:
    """Extract samples by category from JSONL file."""
    asm_samples = []
    oos_samples = []
    debug_samples = []

    with open(jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Get quality score
            quality = sample.get("quality_score", 0)
            if quality < QUALITY_THRESHOLD:
                continue

            # Combine text for matching
            text = " ".join([
                sample.get("instruction", ""),
                sample.get("output", ""),
                sample.get("input", "")
            ])

            # Categorize
            if matches_keywords(text, OOS_KEYWORDS):
                oos_samples.append(sample)
            elif matches_keywords(text, ASM_KEYWORDS):
                asm_samples.append(sample)

            if matches_keywords(text, DEBUG_KEYWORDS):
                debug_samples.append(sample)

    return asm_samples, oos_samples, debug_samples

def format_for_training(sample: dict, expert: str) -> dict:
    """Format sample for expert training."""
    return {
        "input": sample.get("instruction", ""),
        "output": sample.get("output", ""),
        "context": sample.get("input", ""),
        "domain": sample.get("domain", "unknown"),
        "source": f"chat_distillation_{sample.get('source', 'unknown')}",
        "timestamp": sample.get("timestamp", datetime.now().isoformat()),
        "metadata": {
            "expert": expert,
            "original_quality": sample.get("quality_score", 0),
            "teacher_model": sample.get("teacher_model", "unknown"),
            "tags": ["distillation", expert],
        }
    }

def main():
    print("Extracting training samples from chat logs...")

    all_asm = []
    all_oos = []
    all_debug = []

    # Process each dataset
    datasets = [
        ("claude_export.jsonl", "claude"),
        ("gemini_export.jsonl", "gemini"),
        ("codex_export.jsonl", "codex"),
        ("scawful_chatml.jsonl", "scawful"),
    ]

    for filename, domain in datasets:
        path = DATASETS_DIR / filename
        if not path.exists():
            print(f"  Skipping {filename} (not found)")
            continue

        print(f"Processing {filename}...")
        asm, oos, debug = extract_samples(path, domain)
        all_asm.extend(asm)
        all_oos.extend(oos)
        all_debug.extend(debug)
        print(f"  ASM: {len(asm)}, OoS: {len(oos)}, Debug: {len(debug)}")

    # Deduplicate by instruction
    def dedupe(samples: list) -> list:
        seen = set()
        result = []
        for s in samples:
            key = s.get("instruction", "")[:100]
            if key and key not in seen:
                seen.add(key)
                result.append(s)
        return result

    all_asm = dedupe(all_asm)
    all_oos = dedupe(all_oos)
    all_debug = dedupe(all_debug)

    print(f"\nAfter deduplication:")
    print(f"  ASM samples: {len(all_asm)}")
    print(f"  OoS samples: {len(all_oos)}")
    print(f"  Debug samples: {len(all_debug)}")

    # Format and save
    # For Veran (hardware knowledge)
    veran_samples = [format_for_training(s, "veran") for s in all_asm[:500]]

    # For Farore (debugging)
    farore_samples = [format_for_training(s, "farore") for s in all_debug[:500]]

    # For Oracle specialist
    oracle_samples = [format_for_training(s, "oracle_specialist") for s in all_oos[:500]]

    # Save outputs
    outputs = [
        ("chat_veran_distill.jsonl", veran_samples),
        ("chat_farore_distill.jsonl", farore_samples),
        ("chat_oracle_distill.jsonl", oracle_samples),
    ]

    for filename, samples in outputs:
        path = OUTPUT_DIR / filename
        with open(path, "w") as f:
            for sample in samples:
                f.write(json.dumps(sample) + "\n")
        print(f"Saved {len(samples)} samples to {path}")

    # Summary
    summary = {
        "extracted_at": datetime.now().isoformat(),
        "sources": [d[0] for d in datasets],
        "quality_threshold": QUALITY_THRESHOLD,
        "counts": {
            "asm_total": len(all_asm),
            "oos_total": len(all_oos),
            "debug_total": len(all_debug),
            "veran_saved": len(veran_samples),
            "farore_saved": len(farore_samples),
            "oracle_saved": len(oracle_samples),
        }
    }

    summary_path = OUTPUT_DIR / "chat_extraction_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to {summary_path}")

if __name__ == "__main__":
    main()
