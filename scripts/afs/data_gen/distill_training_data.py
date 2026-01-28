#!/usr/bin/env python3
"""
Distillation Training Data Filter
Aggressively filters and categorizes training data by expert domain.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Domain classification keywords
DOMAIN_KEYWORDS = {
    "farore_debug": {
        "strong": [
            "bug", "crash", "fix", "debug", "broken", "wrong value", "corrupt",
            "stack imbalance", "register mode", "mismatch", "why does", "doesn't work",
            "trace", "diagnose", "issue", "problem", "error"
        ],
        "code_patterns": [
            r"PHA.*without.*PL[AXY]",  # Stack imbalance
            r"SEP.*REP",  # Mode switching
            r"missing|forgot",  # Common bug descriptions
            r"crash|hang|freeze",
        ],
        "required": ["65816", "asm", "snes", "alttp", "zelda", "sprite", "routine"]
    },
    "veran_hardware": {
        "strong": [
            "register", "dma", "hdma", "ppu", "vram", "oam", "cgram",
            "scanline", "mode 7", "palette", "tilemap", "vblank", "nmi",
            "$21", "$42", "$43", "vmain", "inidisp", "obsel", "bgmode"
        ],
        "code_patterns": [
            r"\$21[0-9A-F]{2}",  # PPU registers
            r"\$42[0-9A-F]{2}",  # CPU/DMA registers
            r"\$43[0-9A-F]{2}",  # DMA channel registers
            r"DMA[0-7]",
            r"VRAM|OAM|CGRAM",
        ],
        "required": []
    },
    "din_optimize": {
        "strong": [
            "optimize", "optimization", "faster", "performance", "cycle", "cycles",
            "cycle count", "save cycles", "speed", "tighten", "micro-opt",
            "instruction count", "throughput", "latency"
        ],
        "code_patterns": [
            r"\boptimi[sz]e\b",
            r"\bperformance\b",
            r"\bcycle(?:s| count)?\b",
            r"\bfaster\b",
            r"\bspeed\b",
            r"\brefactor\b.*\b(speed|size)\b",
        ],
        "required": ["optimize", "optimization", "performance", "cycle", "cycles", "faster", "speed"]
    },
    "nayru_codegen": {
        "strong": [
            "write", "create", "generate", "implement", "code for",
            "routine that", "function to", "how would i", "assembly for"
        ],
        "code_patterns": [
            r"^(Write|Create|Generate|Implement)",
        ],
        "required": []
    },
    "majora_oracle": {
        "strong": [
            "oracle", "oos", "time system", "mask system", "zsow", "zscream",
            "minecart", "ocarina", "lost woods", "ranch", "custom sprite"
        ],
        "code_patterns": [
            r"Oracle_",
            r"OOS_",
            r"ZS[OC]_",
            r"Mask_",
            r"Time_",
        ],
        "required": []
    },
    "agahnim_build": {
        "strong": [
            "asar", "hook", "namespace", "pushpc", "pullpc", "org", "incsrc",
            "bank", "include", "assert", "label"
        ],
        "code_patterns": [
            r"pushpc|pullpc",
            r"namespace\s+\w+",
            r"org\s+\$",
            r"incsrc",
        ],
        "required": []
    }
}

# System prompts for each expert
SYSTEM_PROMPTS = {
    "farore_debug": """You are Farore, a 65816 assembly debugging expert for SNES ROM hacking.

Your expertise:
- Identifying bugs in 65816 assembly code
- Diagnosing crashes, hangs, and visual glitches
- Finding register mode mismatches (8-bit vs 16-bit)
- Stack corruption and imbalance detection
- Memory corruption patterns

When debugging:
1. Identify the symptom (crash, wrong value, visual bug)
2. Trace the code path to find the issue
3. Explain the root cause
4. Provide a minimal fix with explanation""",

    "veran_hardware": """You are Veran, a SNES hardware expert specializing in 65816 assembly.

Your expertise:
- PPU registers ($2100-$213F) and graphics pipeline
- DMA/HDMA configuration and timing
- VRAM, OAM, and CGRAM operations
- Mode 7 matrix transformations
- Scanline timing and VBlank synchronization

When explaining hardware:
1. Provide register addresses and names
2. Explain bit fields and valid values
3. Show example code for operations
4. Note timing constraints and gotchas""",

    "din_optimize": """You are Din, a 65816 assembly optimization expert.

Your expertise:
- Reducing cycle counts and instruction count
- Improving memory access patterns safely
- Preserving behavior while optimizing
- Avoiding mode and bank side effects

When optimizing:
1. Preserve semantics first
2. Provide optimized 65816 assembly
3. Note any tradeoffs briefly if relevant""",

    "nayru_codegen": """You are Nayru, a 65816 assembly code generation expert.

Your expertise:
- Writing clean, efficient 65816 assembly
- DMA transfers, sprite handling, input processing
- Memory operations and bank switching
- Optimizing for SNES constraints

When generating code:
1. Start with ```asm immediately
2. Include comments explaining each section
3. Use proper SEP/REP for register modes
4. Provide complete, working code""",

    "majora_oracle": """You are Majora, an expert on the Oracle of Secrets ROM hack for A Link to the Past.

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
4. Use OoS naming conventions""",

    "agahnim_build": """You are Agahnim, a 65816 build and integration expert for asar assembler.

Your expertise:
- asar directives (org, pushpc/pullpc, incsrc, assert)
- Namespace management and exports
- Hook patterns for vanilla code modification
- Bank allocation and ROM layout
- Include order and dependency management

When providing solutions:
1. Use proper pushpc/pullpc for patches
2. Include namespace blocks when needed
3. Add boundary assertions for safety
4. Explain include order requirements"""
}


def classify_sample(text: str) -> Tuple[str, float]:
    """Classify a sample into a domain with confidence score."""
    text_lower = text.lower()
    scores = defaultdict(float)

    for domain, keywords in DOMAIN_KEYWORDS.items():
        # Check strong keywords
        for kw in keywords["strong"]:
            if kw.lower() in text_lower:
                scores[domain] += 2.0

        # Check code patterns
        for pattern in keywords["code_patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                scores[domain] += 3.0

        # Check required keywords (must have at least one)
        if keywords["required"]:
            has_required = any(req.lower() in text_lower for req in keywords["required"])
            if not has_required:
                scores[domain] = 0  # Disqualify if missing required

    if not scores:
        return "general", 0.0

    best_domain = max(scores, key=scores.get)
    confidence = scores[best_domain] / 10.0  # Normalize to 0-1 range
    return best_domain, min(confidence, 1.0)


def is_high_quality(sample: dict) -> bool:
    """Check if sample meets quality threshold."""
    output = sample.get("output", "")
    instruction = sample.get("instruction", "")

    # Must have substantial output
    if len(output) < 50:
        return False

    # Must have clear instruction
    if len(instruction) < 10:
        return False

    # Should contain ASM-like content
    asm_indicators = ["$", "LDA", "STA", "JSR", "JSL", "RTS", "RTL", "#$", "db ", "dw "]
    has_asm = any(ind in output for ind in asm_indicators)

    return has_asm


def convert_to_chatml(sample: dict, domain: str) -> dict:
    """Convert sample to ChatML format with appropriate system prompt."""
    system_prompt = SYSTEM_PROMPTS.get(domain, SYSTEM_PROMPTS["nayru_codegen"])

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # Build user message
    user_content = sample.get("instruction", "")
    if sample.get("input"):
        user_content += f"\n\n{sample['input']}"

    messages.append({"role": "user", "content": user_content})

    # Build assistant message with optional thinking
    assistant_content = ""
    if sample.get("thinking"):
        assistant_content = f"<thinking>\n{sample['thinking']}\n</thinking>\n\n"
    assistant_content += sample.get("output", "")

    messages.append({"role": "assistant", "content": assistant_content})

    return {"messages": messages}


def process_file(filepath: Path) -> Dict[str, List[dict]]:
    """Process a JSONL file and categorize samples by domain."""
    categorized = defaultdict(list)

    with open(filepath) as f:
        for line in f:
            try:
                sample = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if not is_high_quality(sample):
                continue

            # Combine all text for classification
            text = " ".join([
                sample.get("instruction", ""),
                sample.get("input", ""),
                sample.get("output", "")
            ])

            domain, confidence = classify_sample(text)

            if confidence >= 0.3:  # Minimum confidence threshold
                chatml = convert_to_chatml(sample, domain)
                chatml["_meta"] = {
                    "source": filepath.name,
                    "domain": domain,
                    "confidence": confidence
                }
                categorized[domain].append(chatml)

    return categorized


def resolve_dataset_path(datasets_dir: Path, filename: str) -> Path | None:
    """Locate a dataset file across common dataset subfolders."""
    search_roots = [
        datasets_dir,
        datasets_dir / "sources",
        datasets_dir / "archive" / "intermediate",
        datasets_dir / "archive",
        datasets_dir / "jsonl",
    ]
    for root in search_roots:
        candidate = root / filename
        if candidate.exists():
            return candidate
    return None


def main():
    datasets_dir = Path.home() / "src/training/datasets"
    output_dir = Path.home() / "src/lab/afs/training_data/filtered"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Files to process (prioritize high-quality sources)
    priority_files = [
        "asm_gold_asar_pass_20260102.jsonl",
        "asm_augmented_20260101.jsonl",
        "oos_enriched_v1_normalized_notodo_asar_pass.jsonl",  # Oracle of Secrets enriched (6,281 samples)
        "asm_git_oracle-of-secrets_20251231_213350.jsonl",
        "asm_git_oracle_20251231_211447.jsonl",
        "asm_comment_to_code_sample_1000_asar_pass_20251231_214207.jsonl",
        "asm_docs_sections_20251231_213427.jsonl",
        "asm_analysis_structured_20251231_212609.jsonl",
    ]

    all_categorized = defaultdict(list)

    for filename in priority_files:
        filepath = resolve_dataset_path(datasets_dir, filename)
        if not filepath:
            print(f"Skipping {filename} (not found)")
            continue

        print(f"Processing {filename}...")
        categorized = process_file(filepath)

        for domain, samples in categorized.items():
            all_categorized[domain].extend(samples)
            print(f"  {domain}: {len(samples)} samples")

    # Write filtered datasets
    print("\n=== Writing filtered datasets ===")
    for domain, samples in all_categorized.items():
        output_file = output_dir / f"{domain}_filtered.jsonl"
        with open(output_file, "w") as f:
            for sample in samples:
                f.write(json.dumps(sample) + "\n")
        print(f"{domain}: {len(samples)} samples -> {output_file.name}")

    # Summary
    print("\n=== Summary ===")
    total = sum(len(s) for s in all_categorized.values())
    print(f"Total high-quality samples: {total}")
    for domain, samples in sorted(all_categorized.items(), key=lambda x: -len(x[1])):
        print(f"  {domain}: {len(samples)}")


if __name__ == "__main__":
    main()
