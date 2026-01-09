#!/usr/bin/env python3
"""
Process Oracle of Secrets Enriched Dataset
Converts ALL OOS samples to Majora training format.
"""

import json
from pathlib import Path

# Majora system prompt
MAJORA_SYSTEM_PROMPT = """You are Majora, an expert on the Oracle of Secrets ROM hack for A Link to the Past.

Your expertise:
- Oracle of Secrets codebase and architecture
- Time System, Mask System, Custom Menus
- ZSCustomOverworld (ZSOW) integration
- Custom sprites and boss implementations
- Namespace bridging (Oracle_*, ZSO_*)

When answering:
1. Reference specific files when possible
2. Explain how systems interact
3. Warn about known integration issues
4. Use OoS naming conventions"""


def convert_to_chatml(sample: dict) -> dict:
    """Convert OOS sample to ChatML format for Majora."""
    messages = [
        {"role": "system", "content": MAJORA_SYSTEM_PROMPT}
    ]

    # Build user message
    user_content = sample.get("instruction", "")
    if sample.get("input"):
        user_content += f"\n\n{sample['input']}"

    messages.append({"role": "user", "content": user_content})

    # Build assistant message
    assistant_content = sample.get("output", "")
    messages.append({"role": "assistant", "content": assistant_content})

    return {
        "messages": messages,
        "_meta": {
            "source": "oos_enriched_v1_normalized_notodo_asar_pass",
            "domain": "majora_oracle",
            "confidence": 0.8,  # Medium-high confidence for Oracle codebase samples
            "oracle_enriched": True
        }
    }


def is_high_quality(sample: dict) -> bool:
    """Check if sample meets quality threshold (relaxed for Oracle codebase)."""
    output = sample.get("output", "")
    instruction = sample.get("instruction", "")

    # Relaxed: accept shorter output for Oracle samples (code snippets are valuable)
    if len(output) < 20:
        return False

    # Must have clear instruction
    if len(instruction) < 10:
        return False

    # Should contain ASM-like content
    asm_indicators = ["$", "LDA", "STA", "JSR", "JSL", "RTS", "RTL", "#$", "db ", "dw ", ";", "namespace"]
    has_asm = any(ind in output for ind in asm_indicators)

    return has_asm


def main():
    oos_file = Path.home() / "src/training/datasets/oos_enriched_v1_normalized_notodo_asar_pass.jsonl"
    output_file = Path.home() / "src/lab/afs/training_data/filtered/majora_oracle_oos_enriched.jsonl"

    print("Processing Oracle of Secrets enriched dataset...")
    print(f"Input: {oos_file}")
    print(f"Output: {output_file}")
    print()

    processed = []
    skipped = 0

    with open(oos_file) as f:
        for line_num, line in enumerate(f, 1):
            try:
                sample = json.loads(line.strip())
            except json.JSONDecodeError:
                skipped += 1
                continue

            if not is_high_quality(sample):
                skipped += 1
                continue

            chatml = convert_to_chatml(sample)
            processed.append(chatml)

            if line_num % 1000 == 0:
                print(f"  Processed {line_num} samples...")

    # Write to output
    with open(output_file, "w") as f:
        for sample in processed:
            f.write(json.dumps(sample) + "\n")

    print()
    print("=== Summary ===")
    print(f"Total samples processed: {len(processed)}")
    print(f"Skipped (low quality): {skipped}")
    print(f"Output: {output_file}")
    print()
    print(f"✓ All Oracle of Secrets samples converted to Majora training format")


if __name__ == "__main__":
    main()
