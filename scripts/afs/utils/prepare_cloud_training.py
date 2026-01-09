#!/usr/bin/env python3
"""Prepare training data for cloud GPU training.

Combines all training pools into properly formatted JSONL for LoRA training.
"""

import json
from pathlib import Path
from datetime import datetime

TRAINING_POOLS = Path.home() / ".context/training_pools"
OUTPUT_DIR = Path.home() / "src/lab/afs/training_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def convert_to_chatml(sample: dict) -> dict:
    """Convert sample to ChatML format for training."""
    messages = []

    # System message for expert context
    expert = sample.get("metadata", {}).get("expert", "assistant")
    system_prompts = {
        "farore": "You are Farore, a 65816 assembly debugging expert. Analyze bugs, identify issues, and explain fixes.",
        "veran": "You are Veran, a 65816 assembly hardware expert. Explain SNES hardware, registers, and low-level operations.",
        "oracle_specialist": "You are an expert on the Oracle of Secrets ALTTP ROM hack. Explain code, systems, and implementations.",
    }

    system_msg = system_prompts.get(expert, "You are a helpful 65816 assembly expert.")
    messages.append({"role": "system", "content": system_msg})

    # User message (input/instruction)
    user_content = sample.get("input", sample.get("instruction", ""))
    if user_content:
        messages.append({"role": "user", "content": user_content})

    # Assistant message (output)
    assistant_content = sample.get("output", "")
    if assistant_content:
        messages.append({"role": "assistant", "content": assistant_content})

    return {"messages": messages}

def load_jsonl(path: Path) -> list[dict]:
    """Load samples from JSONL file."""
    samples = []
    if not path.exists():
        return samples
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return samples

def main():
    print("Preparing cloud training data...")

    # Farore training data (debugging)
    farore_sources = [
        ("chat_farore_distill.jsonl", "chat"),
        ("oos_bugfix_samples.jsonl", "git"),
    ]

    farore_samples = []
    for filename, source in farore_sources:
        samples = load_jsonl(TRAINING_POOLS / filename)
        for s in samples:
            s.setdefault("metadata", {})["expert"] = "farore"
        farore_samples.extend(samples)
        print(f"  Loaded {len(samples)} from {filename}")

    # Veran training data (hardware)
    veran_sources = [
        ("chat_veran_distill.jsonl", "chat"),
        ("veran_critical_training.jsonl", "critical"),
    ]

    veran_samples = []
    for filename, source in veran_sources:
        samples = load_jsonl(TRAINING_POOLS / filename)
        for s in samples:
            s.setdefault("metadata", {})["expert"] = "veran"
        veran_samples.extend(samples)
        print(f"  Loaded {len(samples)} from {filename}")

    # Oracle specialist training data
    oracle_sources = [
        ("chat_oracle_distill.jsonl", "chat"),
        ("oos_feature_samples.jsonl", "git"),
    ]

    oracle_samples = []
    for filename, source in oracle_sources:
        samples = load_jsonl(TRAINING_POOLS / filename)
        for s in samples:
            s.setdefault("metadata", {})["expert"] = "oracle_specialist"
        oracle_samples.extend(samples)
        print(f"  Loaded {len(samples)} from {filename}")

    # Convert and save
    outputs = [
        ("farore_training.jsonl", farore_samples),
        ("veran_training.jsonl", veran_samples),
        ("oracle_training.jsonl", oracle_samples),
    ]

    for filename, samples in outputs:
        output_path = OUTPUT_DIR / filename
        chatml_samples = [convert_to_chatml(s) for s in samples]

        # Filter out empty samples
        chatml_samples = [s for s in chatml_samples if len(s["messages"]) >= 2]

        with open(output_path, "w") as f:
            for sample in chatml_samples:
                f.write(json.dumps(sample) + "\n")

        print(f"\nSaved {len(chatml_samples)} samples to {output_path}")

    # Create upload manifest
    manifest = {
        "created": datetime.now().isoformat(),
        "files": {
            "farore_training.jsonl": len(farore_samples),
            "veran_training.jsonl": len(veran_samples),
            "oracle_training.jsonl": len(oracle_samples),
        },
        "total_samples": len(farore_samples) + len(veran_samples) + len(oracle_samples),
    }

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest saved to {manifest_path}")
    print(f"Total training samples: {manifest['total_samples']}")
    print(f"\nUpload to cloud with:")
    print(f"  scp -P <port> {OUTPUT_DIR}/*.jsonl root@<vast-host>:/workspace/")

if __name__ == "__main__":
    main()
