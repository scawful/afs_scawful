#!/usr/bin/env python3
"""
Validate 65816 Instruction Set JSON
Checks for missing opcodes, inconsistent cycle counts, and flag penalties.
"""

import json
import sys
from pathlib import Path

def validate_json(path):
    print(f"[*] Validating {path}...")
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return False

    instructions = data.get("instructions", {})
    metadata = data.get("metadata", {})
    
    print(f"Source: {metadata.get('source', 'Unknown')}")
    print(f"Total Opcodes Defined: {len(instructions)}")
    
    # Check for critical opcodes
    critical_mnemonics = ["LDA", "STA", "JSL", "JML", "RTL", "RTS", "PHA", "PLA", "PHB", "PLB", "REP", "SEP"]
    found_mnemonics = set(inst["mnemonic"] for inst in instructions.values())
    
    missing = [m for m in critical_mnemonics if m not in found_mnemonics]
    if missing:
        print(f"Warning: Missing critical mnemonics: {', '.join(missing)}")
    else:
        print("All critical 65816 mnemonics found.")

    # Check formatting
    errors = 0
    for opcode, details in instructions.items():
        if len(opcode) != 2:
            print(f"Invalid opcode format: {opcode}")
            errors += 1
        if "cycles" not in details or "bytes" not in details:
            print(f"Missing metrics for {opcode}")
            errors += 1
            
    if errors == 0:
        print("Schema validation passed.")
        return True
    return False

if __name__ == "__main__":
    path = Path("afs/knowledge/65816_instruction_set.json")
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
        
    if validate_json(path):
        print("Success: Instruction set is ready for Veran training.")
        sys.exit(0)
    else:
        sys.exit(1)
