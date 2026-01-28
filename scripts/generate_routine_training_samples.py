#!/usr/bin/env python3
"""
Generate instruction-following training samples from the master_routines_library.json file.

Input: ~/src/lab/afs-scawful/data/master_routines_library.json (8,252 assembly routines)
Output: ~/.context/training/datasets/routines_instruction_samples.jsonl

This script generates training samples for fine-tuning LLMs on 65816 assembly code
from the Legend of Zelda: A Link to the Past disassembly.
"""

import json
import os
import re
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Paths
INPUT_FILE = Path.home() / "src/lab/afs-scawful/data/master_routines_library.json"
OUTPUT_FILE = Path.home() / ".context/training/datasets/routines_instruction_samples.jsonl"


def is_data_only_routine(code: str) -> bool:
    """
    Check if a routine contains only data declarations (incbin, db, dw statements).
    These are skipped as they don't provide instructional value for code explanation.
    """
    lines = code.strip().split('\n')

    for line in lines:
        # Remove address prefixes like #_09ADF4:
        clean_line = re.sub(r'#_[0-9A-Fa-f]+:\s*', '', line).strip()

        # Skip empty lines, comments, and labels
        if not clean_line or clean_line.startswith(';') or clean_line.endswith(':'):
            continue

        # Skip pure section markers
        if clean_line.startswith('==='):
            continue

        # Check if this is a data declaration
        lower_line = clean_line.lower()
        is_data = any(lower_line.startswith(prefix) for prefix in [
            'incbin', 'db ', 'dw ', 'dl ', 'dd ', '.db', '.dw', '.dl',
            'gfx_', 'null_'
        ])

        # If we find any non-data instruction, it's not data-only
        if not is_data:
            return False

    return True


def is_room_data(name: str) -> bool:
    """Check if this is room/level data that should be skipped."""
    skip_patterns = [
        r'^RoomData_',
        r'^OverworldMap32_',
        r'^NULL_',
        r'^LinkGraphics$',
        r'^GFX_',
        r'^UNREACHABLE_',
    ]
    return any(re.match(pattern, name) for pattern in skip_patterns)


def clean_code_for_training(code: str) -> str:
    """Clean code by removing address prefixes for cleaner training data."""
    lines = []
    for line in code.split('\n'):
        # Remove address prefixes like #_09ADF4:
        clean_line = re.sub(r'#_[0-9A-Fa-f]+:\s*', '', line)
        lines.append(clean_line)
    return '\n'.join(lines).strip()


def extract_routine_info(name: str, code: str) -> Dict[str, str]:
    """Extract information about what a routine does based on its name and code."""
    info = {
        'category': 'unknown',
        'entity': None,
        'action': None,
    }

    # Categorize by name patterns
    if name.startswith('Sprite_'):
        info['category'] = 'sprite_behavior'
        match = re.match(r'Sprite_([0-9A-F]+)_(\w+)', name)
        if match:
            info['entity'] = match.group(2)
            info['action'] = 'main behavior'
        else:
            match = re.match(r'Sprite_(\w+)', name)
            if match:
                info['action'] = match.group(1).replace('_', ' ')

    elif name.startswith('SpritePrep_'):
        info['category'] = 'sprite_initialization'
        match = re.match(r'SpritePrep_(\w+)', name)
        if match:
            info['action'] = match.group(1).replace('_', ' ')

    elif name.startswith('Garnish'):
        info['category'] = 'visual_effect'
        match = re.match(r'Garnish([0-9A-F]+)?_?(\w+)?', name)
        if match and match.group(2):
            info['entity'] = match.group(2)

    elif name.startswith('Link_'):
        info['category'] = 'player_action'
        match = re.match(r'Link_(\w+)', name)
        if match:
            info['action'] = match.group(1).replace('_', ' ')

    elif name.startswith('Ancilla_'):
        info['category'] = 'ancilla_effect'
        match = re.match(r'Ancilla_(\w+)', name)
        if match:
            info['action'] = match.group(1).replace('_', ' ')

    elif name.startswith('DashDust_') or name.startswith('Fireball_'):
        info['category'] = 'effect'
        match = re.match(r'(\w+)_(\w+)', name)
        if match:
            info['entity'] = match.group(1)
            info['action'] = match.group(2).replace('_', ' ')

    elif 'Check' in name:
        info['category'] = 'check_condition'
        info['action'] = name.replace('_', ' ')

    elif 'Spawn' in name:
        info['category'] = 'spawn_entity'
        info['action'] = name.replace('_', ' ')

    elif 'Initialize' in name or 'Init' in name:
        info['category'] = 'initialization'
        info['action'] = name.replace('_', ' ')

    elif 'Draw' in name:
        info['category'] = 'graphics'
        info['action'] = name.replace('_', ' ')

    elif 'Move' in name:
        info['category'] = 'movement'
        info['action'] = name.replace('_', ' ')

    elif 'Damage' in name:
        info['category'] = 'damage_system'
        info['action'] = name.replace('_', ' ')

    else:
        # Extract action from camelCase or underscore names
        info['action'] = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        info['action'] = info['action'].replace('_', ' ')

    return info


def analyze_code_patterns(code: str) -> List[str]:
    """Analyze code to identify common patterns and techniques used."""
    patterns = []

    code_upper = code.upper()

    # Detect common 65816 patterns
    if 'PHB' in code_upper and 'PLB' in code_upper:
        patterns.append('bank switching with data bank register preservation')

    if 'PHX' in code_upper and 'PLX' in code_upper:
        patterns.append('X register preservation')

    if 'PHY' in code_upper and 'PLY' in code_upper:
        patterns.append('Y register preservation')

    if 'REP #$30' in code_upper or 'REP #$20' in code_upper:
        patterns.append('16-bit mode switching')

    if 'SEP #$30' in code_upper or 'SEP #$20' in code_upper:
        patterns.append('8-bit mode switching')

    if 'JSL' in code_upper:
        patterns.append('long subroutine calls')

    if 'RTL' in code_upper:
        patterns.append('long return from subroutine')

    if 'JUMPTABLELOCAL' in code_upper:
        patterns.append('state machine using jump table')

    if re.search(r'\bLDX\b.*#\$0[0-9A-F]\b.*\bDEX\b.*\bBPL\b', code_upper, re.DOTALL):
        patterns.append('loop with counter')

    if '$0DD0' in code or '$0D10' in code or '$0D00' in code:
        patterns.append('sprite state/position manipulation')

    if 'GETRANDOMNUMBER' in code_upper:
        patterns.append('random number generation')

    if 'OAM' in code_upper:
        patterns.append('OAM (sprite) manipulation')

    if 'SFX' in code_upper:
        patterns.append('sound effect triggering')

    return patterns


def generate_explanation(name: str, code: str, info: Dict) -> str:
    """Generate a human-readable explanation of what a routine does."""
    patterns = analyze_code_patterns(code)

    # Count lines of actual code (not comments/empty)
    code_lines = [l for l in code.split('\n')
                  if l.strip() and not l.strip().startswith(';') and not l.strip().startswith('===')]
    line_count = len(code_lines)

    explanation_parts = []

    # Category-specific explanations
    category = info.get('category', 'unknown')
    action = info.get('action', name.replace('_', ' '))
    entity = info.get('entity')

    if category == 'sprite_behavior':
        if entity:
            explanation_parts.append(f"This routine implements the main behavior logic for the {entity} sprite.")
        else:
            explanation_parts.append(f"This routine handles sprite behavior: {action}.")

    elif category == 'sprite_initialization':
        explanation_parts.append(f"This routine initializes sprite data: {action}.")

    elif category == 'visual_effect':
        if entity:
            explanation_parts.append(f"This routine handles the visual effect for {entity}.")
        else:
            explanation_parts.append("This routine manages a visual garnish/effect.")

    elif category == 'player_action':
        explanation_parts.append(f"This routine handles Link's (the player character's) action: {action}.")

    elif category == 'ancilla_effect':
        explanation_parts.append(f"This routine manages an ancilla (weapon/item effect): {action}.")

    elif category == 'check_condition':
        explanation_parts.append(f"This routine checks a game condition: {action}.")

    elif category == 'spawn_entity':
        explanation_parts.append(f"This routine spawns a game entity: {action}.")

    elif category == 'initialization':
        explanation_parts.append(f"This routine performs initialization: {action}.")

    elif category == 'graphics':
        explanation_parts.append(f"This routine handles graphics rendering: {action}.")

    elif category == 'movement':
        explanation_parts.append(f"This routine handles movement calculations: {action}.")

    elif category == 'damage_system':
        explanation_parts.append(f"This routine handles the damage system: {action}.")

    else:
        explanation_parts.append(f"This routine implements: {action}.")

    # Add pattern information
    if patterns:
        if len(patterns) == 1:
            explanation_parts.append(f"It uses {patterns[0]}.")
        elif len(patterns) <= 3:
            explanation_parts.append(f"It uses techniques including: {', '.join(patterns)}.")

    # Add size information for context
    if line_count > 50:
        explanation_parts.append("This is a substantial routine with complex logic.")
    elif line_count > 20:
        explanation_parts.append("This is a moderate-sized routine.")

    return ' '.join(explanation_parts)


def generate_task_description(name: str, info: Dict) -> str:
    """Generate a task description for reverse instruction samples."""
    category = info.get('category', 'unknown')
    action = info.get('action', name.replace('_', ' '))
    entity = info.get('entity')

    if category == 'sprite_behavior':
        if entity:
            return f"Implement the main behavior loop for a {entity} enemy sprite in 65816 assembly"
        return f"Write 65816 assembly code to {action.lower()}"

    elif category == 'sprite_initialization':
        return f"Write initialization code for a sprite that handles {action.lower()}"

    elif category == 'visual_effect':
        if entity:
            return f"Create a visual effect routine for {entity}"
        return "Implement a garnish/visual effect routine"

    elif category == 'player_action':
        return f"Implement Link's {action.lower()} action in 65816 assembly"

    elif category == 'check_condition':
        return f"Write a routine to {action.lower()}"

    elif category == 'spawn_entity':
        return f"Write code to {action.lower()}"

    elif category == 'movement':
        return f"Implement {action.lower()} in 65816 assembly"

    else:
        return f"Write 65816 assembly code for: {action.lower()}"


def generate_samples_for_routine(routine: Dict, sample_idx: int,
                                  target_samples: int = 2500,
                                  total_valid_routines: int = 5000) -> List[Dict]:
    """
    Generate 1-3 training samples for a single routine.

    To hit ~2500 samples, we need to be selective:
    - Higher quality routines get more samples
    - Use probability to control overall output
    """
    name = routine['name']
    code = routine['code']
    source_file = routine.get('file', 'unknown')

    # Skip data-only routines and room data
    if is_data_only_routine(code) or is_room_data(name):
        return []

    # Get cleaned code
    clean_code = clean_code_for_training(code)

    # Skip very short routines (just a jump or return)
    code_lines = [l for l in clean_code.split('\n')
                  if l.strip() and not l.strip().startswith(';') and not l.strip().startswith('===')]
    if len(code_lines) < 3:
        return []

    # Extract routine information
    info = extract_routine_info(name, code)

    # Calculate quality score for this routine
    quality_score = 0.0
    patterns = analyze_code_patterns(code)

    # Higher quality if it has interesting patterns
    quality_score += min(len(patterns) * 0.15, 0.6)

    # Higher quality for medium-length routines (not too short, not too long)
    if 8 <= len(code_lines) <= 50:
        quality_score += 0.3
    elif 5 <= len(code_lines) < 8:
        quality_score += 0.15
    elif len(code_lines) > 50:
        quality_score += 0.2  # Still valuable, just complex

    # Boost for interesting categories
    interesting_categories = ['sprite_behavior', 'player_action', 'damage_system', 'spawn_entity']
    if info.get('category') in interesting_categories:
        quality_score += 0.2

    # Cap at 1.0
    quality_score = min(quality_score, 1.0)

    # Use quality score to decide whether to include this routine
    # Target ~2500 samples from ~5000 valid routines
    # With avg ~1.5 samples per routine, we need ~1700 routines
    # That's ~34% of valid routines, so threshold should be low
    selection_threshold = 0.0
    if random.random() > (quality_score * 0.6 + selection_threshold):
        return []

    samples = []

    # Sample Type 1: Explain code (always generate for selected routines)
    explanation = generate_explanation(name, code, info)
    samples.append({
        "instruction": "Explain what this 65816 assembly routine does",
        "input": clean_code,
        "output": explanation,
        "domain": "asm",
        "routine_name": name,
        "source_file": source_file,
        "sample_type": "explain_code"
    })

    # Sample Type 2: What does [name] do? (generate for ~40% of selected routines)
    if random.random() < 0.4:
        samples.append({
            "instruction": f"What is the purpose of the {name} routine?",
            "input": "",
            "output": explanation,
            "domain": "asm",
            "routine_name": name,
            "source_file": source_file,
            "sample_type": "name_purpose"
        })

    # Sample Type 3: Generate code (reverse) - only for high-quality routines
    if len(code_lines) >= 10 and quality_score >= 0.5 and random.random() < 0.3:
        task = generate_task_description(name, info)
        samples.append({
            "instruction": task,
            "input": "",
            "output": clean_code,
            "domain": "asm",
            "routine_name": name,
            "source_file": source_file,
            "sample_type": "generate_code"
        })

    return samples


def main():
    print(f"Loading routines from {INPUT_FILE}...")

    with open(INPUT_FILE, 'r') as f:
        routines = json.load(f)

    print(f"Loaded {len(routines)} routines")

    # Set random seed for reproducibility
    random.seed(42)

    all_samples = []
    skipped_data = 0
    skipped_room = 0
    skipped_short = 0

    for idx, routine in enumerate(routines):
        if idx % 1000 == 0:
            print(f"Processing routine {idx}/{len(routines)}...")

        samples = generate_samples_for_routine(routine, idx)

        if not samples:
            name = routine['name']
            code = routine['code']
            if is_room_data(name):
                skipped_room += 1
            elif is_data_only_routine(code):
                skipped_data += 1
            else:
                skipped_short += 1

        all_samples.extend(samples)

    # Shuffle samples
    random.shuffle(all_samples)

    # Write to JSONL
    print(f"\nWriting {len(all_samples)} samples to {OUTPUT_FILE}...")

    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)

    with open(OUTPUT_FILE, 'w') as f:
        for sample in all_samples:
            f.write(json.dumps(sample) + '\n')

    # Calculate statistics
    sample_types = {}
    categories = {}

    for sample in all_samples:
        st = sample['sample_type']
        sample_types[st] = sample_types.get(st, 0) + 1

        # Count by routine (deduplicate)
        # Note: We can infer category from routine name pattern

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nInput routines: {len(routines)}")
    print(f"Total samples generated: {len(all_samples)}")
    print(f"\nRoutines skipped:")
    print(f"  - Room/map data: {skipped_room}")
    print(f"  - Data declarations only: {skipped_data}")
    print(f"  - Too short (< 3 lines): {skipped_short}")
    print(f"  - Total skipped: {skipped_room + skipped_data + skipped_short}")

    print(f"\nSample distribution by type:")
    for st, count in sorted(sample_types.items()):
        percentage = (count / len(all_samples)) * 100
        print(f"  - {st}: {count} ({percentage:.1f}%)")

    print(f"\nOutput file: {OUTPUT_FILE}")
    print(f"File size: {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.2f} MB")


if __name__ == '__main__':
    main()
