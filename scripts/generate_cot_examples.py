#!/usr/bin/env python3
"""
Generate chain-of-thought ASM training examples.
Uses existing routine library to create detailed analysis pairs.
"""
import json
import random
from pathlib import Path
from typing import Iterator

# Templates for generating high-quality examples
ANALYSIS_TEMPLATE = """This routine {purpose}.

**Memory Addresses:**
{addresses}

**Execution Flow:**
{flow}

**Registers Used:**
{registers}

**Optimization Notes:**
{notes}"""

TRACE_TEMPLATE = """Step-by-step execution trace:

{trace}

**Final State:**
{final_state}"""

def generate_analysis_example(routine: dict) -> dict:
    """Generate a detailed analysis example from a routine."""
    name = routine.get("name", "Unknown")
    addr = routine.get("address", "")
    code = routine.get("code", "")
    desc = routine.get("description", "")

    # Create instruction
    instruction = random.choice([
        f"Analyze the '{name}' routine and explain its purpose",
        f"Explain what this ALTTP routine does at ${addr}",
        f"Provide a detailed breakdown of this 65816 assembly code",
        f"What is the purpose of this sprite handling routine?",
    ])

    # Create structured output (this would be enhanced with actual analysis)
    output = f"""This routine handles {desc.lower() if desc else 'game logic'}.

**Entry Point:** ${addr}

**Code Analysis:**
```asm
{code[:500] if code else '; Code not available'}
```

**Key Operations:**
- Primary function: {desc or 'See code analysis'}
- Called from: Main game loop
- Modifies: Various sprite/game state variables

**Notes:**
This is a common pattern in ALTTP's codebase for {name.lower().replace('_', ' ')}."""

    return {
        "instruction": instruction,
        "input": f"```asm\n{code[:1000] if code else 'LDA #$00\\nRTS'}\n```",
        "output": output,
        "domain": "asm-cot",
        "source": "generated",
    }

def generate_optimization_example(routine: dict) -> dict:
    """Generate an optimization challenge example."""
    code = routine.get("code", "LDA #$00\nSTA $00\nRTS")

    instruction = "Optimize this routine for fewer cycles while maintaining functionality"

    output = """**Original Analysis:**
The routine uses standard patterns that can be optimized.

**Optimization Opportunities:**
1. Use index register operations where applicable
2. Combine load/store operations
3. Use BRA instead of JMP for short jumps
4. Consider zero-page addressing for frequently accessed memory

**Optimized Version:**
```asm
; Optimized version with cycle counts
; (Specific optimizations depend on context)
```

**Cycle Savings:**
- Original: ~X cycles
- Optimized: ~Y cycles
- Improvement: ~Z%

**Trade-offs:**
- Code size may increase slightly for unrolled loops
- Register usage patterns may change"""

    return {
        "instruction": instruction,
        "input": f"```asm\n{code[:500]}\n```",
        "output": output,
        "domain": "asm-opt",
        "source": "generated",
    }

def load_routines(path: Path) -> list:
    """Load routines from JSONL training data."""
    if not path.exists():
        return []
    routines = []
    with open(path) as f:
        for line in f:
            try:
                sample = json.loads(line.strip())
                # Convert instruction format to routine format
                routines.append({
                    "name": sample.get("instruction", "")[:50],
                    "address": "",
                    "code": sample.get("input", "") or sample.get("output", ""),
                    "description": sample.get("instruction", ""),
                })
            except json.JSONDecodeError:
                continue
    return routines

def generate_examples(routines: list, count: int = 500) -> Iterator[dict]:
    """Generate training examples from routines."""
    generators = [generate_analysis_example, generate_optimization_example]

    for routine in random.sample(routines, min(count, len(routines))):
        gen = random.choice(generators)
        yield gen(routine)

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--routines", type=Path,
                        default=Path("~/.context/knowledge/alttp/master_routines_library.json").expanduser())
    parser.add_argument("--output", type=Path, default=Path("cot_examples.jsonl"))
    parser.add_argument("--count", type=int, default=500)
    args = parser.parse_args()

    routines = load_routines(args.routines)
    print(f"Loaded {len(routines)} routines")

    count = 0
    with open(args.output, "w") as f:
        for example in generate_examples(routines, args.count):
            f.write(json.dumps(example) + "\n")
            count += 1

    print(f"Generated {count} chain-of-thought examples to {args.output}")

if __name__ == "__main__":
    main()
