#!/usr/bin/env python3
"""
Synthetic Training Example Generator
Generates high-quality synthetic examples for under-represented domains.
"""

import json
import random
from pathlib import Path
from typing import List, Dict

# System prompts from distill_training_data.py
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

# Agahnim build/integration templates
AGAHNIM_TEMPLATES = [
    {
        "instruction": "How do I hook into vanilla ALTTP code at {address} to call my custom routine {routine_name}?",
        "thinking": "The user wants to intercept vanilla code execution. I need to provide a pushpc/pullpc pattern that preserves the original context and jumps to their custom code.",
        "output": """```asm
pushpc
org {address}
    JSL {routine_name}
    NOP  ; Pad if original instruction was larger
pullpc

{routine_name}:
    ; Your custom code here

    ; Execute original vanilla code if needed
    ; [original instruction that was replaced]

    RTL
```

**Important notes:**
- `pushpc` saves current assembly position
- `org` jumps to vanilla address
- `JSL` is a long jump (crosses banks)
- `NOP` pads space if original was > 4 bytes
- `pullpc` returns to previous position
- `RTL` returns from long call

**Bank allocation:** Ensure {routine_name} is in a free bank (typically $2B-$3F for Oracle)."""
    },
    {
        "instruction": "I'm getting 'overwrote some code' error when assembling. How do I add boundary checks?",
        "thinking": "Assembly overflow into unallocated space. Need to show assert directive usage for bank boundaries.",
        "output": """Use `assert` directives to catch bank overflow during assembly:

```asm
org $2B8000
; ... your code ...

; At end of bank, add boundary check
assert pc() <= $2BFFFF, \"Bank $2B overflow! Used: \", pc() - $2B8000, \" bytes\"
```

**pc() function:** Returns current program counter (assembly position)

**Common bank boundaries:**
- Bank $2B (Items): $2B8000 - $2BFFFF (32KB)
- Bank $2C (Dungeons): $2C8000 - $2CFFFF
- Bank $2D (Menus): $2D8000 - $2DFFFF

**If you overflow:**
1. Move code to different bank
2. Optimize/compress existing code
3. Use `incsrc` to split across files

**Check bank usage:**
```asm
!bank_start = $2B8000
org !bank_start
; ... code ...
!bank_used = pc() - !bank_start
assert !bank_used <= $8000, \"Bank used: \", !bank_used, \" / 32768 bytes\"
```"""
    },
    {
        "instruction": "How do I export a label from namespace {namespace} so other files can call it?",
        "thinking": "Namespace export for cross-file visibility. Show both internal definition and external export pattern.",
        "output": """**Inside namespace block:**

```asm
namespace {namespace}
{{
    ; Define your routine inside namespace
    MyRoutine:
        ; Implementation
        RTL

    ; Export at end of namespace
    ; This creates {namespace}_MyRoutine label
}}
```

**From outside namespace:**

```asm
; Call using namespace prefix
JSL {namespace}_MyRoutine
```

**For ZScream integration (no namespace):**

```asm
; ZScream code lives outside namespace
ZSO_CustomHook:
    ; Implementation
    RTL

; Bridge into Oracle namespace
namespace Oracle
{{
    Oracle_ZSO_CustomHook = ZSO_CustomHook
}}
```

**Include order matters:**
1. Define the label first (in defining file)
2. Include that file before files that reference it
3. Check Oracle_main.asm for correct incsrc order"""
    },
    {
        "instruction": "What's the difference between org, pushpc/pullpc, and namespace in asar?",
        "thinking": "Fundamental asar directive comparison. Need clear explanation with examples showing when to use each.",
        "output": """**org - Set Assembly Position**
```asm
org $2B8000  ; Start writing at bank $2B
; All following code goes here
```
Use for: Allocating new code in free ROM space

---

**pushpc/pullpc - Temporary Patches**
```asm
pushpc
org $00F000  ; Patch vanilla location temporarily
    JSL MyHook
pullpc
; Back to previous org context
```
Use for: Hooking vanilla code without losing your place

---

**namespace - Label Organization**
```asm
namespace Oracle
{{
    MyFunction:  ; Creates Oracle_MyFunction
        RTL
}}

; Call it
JSL Oracle_MyFunction
```
Use for: Organizing labels, preventing name collisions

---

**Combined example:**
```asm
org $2B8000  ; Allocate in bank $2B

namespace Oracle
{{
    CustomItem:
        ; New item code
        RTL
}}

pushpc
org $00ABCD  ; Hook vanilla item handler
    JSL Oracle_CustomItem
pullpc

; Back to bank $2B, still in Oracle namespace
```"""
    },
    {
        "instruction": "My code calls {routine_a} which then calls {routine_b}, but I'm getting 'label not found' during assembly. What's wrong?",
        "thinking": "Forward reference issue. Labels must be defined before use in asar. Need to explain include order and forward declaration patterns.",
        "output": """**Problem:** asar processes files linearly. {routine_b} isn't defined yet when {routine_a} tries to call it.

**Solution 1: Reorder includes**
```asm
; In Oracle_main.asm
incsrc \"file_with_{routine_b}.asm\"  ; Define {routine_b} first
incsrc \"file_with_{routine_a}.asm\"  ; Now {routine_a} can see it
```

**Solution 2: Forward declaration**
```asm
; At top of file_with_{routine_a}.asm
{routine_b} = $2B9000  ; Declare address (must match actual)

{routine_a}:
    JSL {routine_b}  ; Now assembler knows where it is
    RTL
```

**Solution 3: Use namespace exports**
```asm
; If both in Oracle namespace
namespace Oracle
{{
    {routine_b}:
        RTL
}}

; Later in different file
namespace Oracle
{{
    {routine_a}:
        JSL Oracle_{routine_b}  ; Fully qualified name
        RTL
}}
```

**Best practice:** Group related functions in same file, include utilities before code that uses them."""
    }
]

# Oracle-specific templates (Majora domain)
MAJORA_TEMPLATES = [
    {
        "instruction": "How does the Time System interact with dungeon state in Oracle of Secrets?",
        "thinking": "Time System is a core Oracle mechanic that affects dungeon puzzles, enemy spawns, and NPC dialogue. Need to explain the state flow and integration points.",
        "output": """The Time System in Oracle of Secrets uses three primary components:

**1. Time State ($7EF3C7)**
- $00: Day
- $01: Night
- $02: Twilight (transition)

**2. Dungeon Integration**

```asm
; In Oracle_Dungeon.asm
namespace Oracle
{{
    CheckDungeonTimeState:
        LDA $7EF3C7  ; Current time state
        BEQ .day_puzzles
        CMP #$01 : BEQ .night_puzzles
        ; Twilight falls through to day

    .day_puzzles
        ; Spawn day-only enemies
        LDA #$08 : STA $0E20, X  ; Armos sprite
        RTL

    .night_puzzles
        ; Spawn night-only enemies
        LDA #$1B : STA $0E20, X  ; Stalfos sprite
        RTL
}}
```

**3. State Persistence**

Time state persists across rooms using `$7EF3C7`. When changing time:
1. Update time flag
2. Trigger NMI for palette swap
3. Reload room enemies via `Oracle_RefreshDungeon`
4. Update minimap colors

**Integration points:**
- `Oracle_CheckNightTime` - Called by enemy spawn hooks
- `Oracle_TimeTransition` - Handles day/night switching
- `ZSO_LoadSprites` - ZScream bridge for sprite spawning

**Files:**
- `Oracle/Systems/TimeSystem.asm` - Core time logic
- `Oracle/Dungeons/time_puzzles.asm` - Puzzle integration
- `Oracle/Sprites/time_enemies.asm` - Time-dependent spawns"""
    },
    {
        "instruction": "I'm adding a new mask to the Mask System. What files do I need to modify?",
        "thinking": "Mask System requires graphics, menu integration, effect code, and equip logic. Need comprehensive checklist.",
        "output": """**Files to modify for new mask:**

**1. Graphics** (`Oracle/Graphics/Masks/`)
```asm
; mask_MASKNAME.asm
Oracle_MaskMASSKNAMEGfx:
    incbin \"mask_MASKNAME.chr\"  ; 64 tiles

Oracle_MaskMASSKNAMEPalette:
    dw $0000, $1234, $5678  ; 16 colors
```

**2. Menu Integration** (`Oracle/Menus/MaskMenu.asm`)
```asm
; Add to mask ID table
.mask_ids
    db $00  ; Deku Mask
    db $01  ; Goron Mask
    db $02  ; Zora Mask
    db $03  ; MASKNAME Mask

; Add to mask names
.mask_names
    dw .deku_name, .goron_name, .zora_name, .MASKNAME_name

.MASKNAME_name
    db \"MASKNAME Mask\", $FF
```

**3. Effect Code** (`Oracle/Systems/MaskEffects.asm`)
```asm
namespace Oracle
{{
    MaskMASSKNAMEEffect:
        ; Check if mask is worn
        LDA $7EF3C8 : CMP #$03 : BNE .not_active

        ; Apply mask effect
        ; (stat boosts, transformations, abilities)

    .not_active
        RTL
}}
```

**4. Equipment Slot** (`Oracle/Items/mask_equip.asm`)
```asm
; Hook into equipment change
pushpc
org $00D7A2  ; Vanilla equipment handler
    JSL Oracle_HandleMaskEquip
pullpc
```

**5. Bank Allocation**
- Graphics: Bank $33-$34 (Masks)
- Code: Bank $2D (Menu) + $2E (Effects)
- Data: Bank $35 (Strings)

**6. Save Data**
```asm
$7EF3C8   ; Current equipped mask ID
$7EF3D0   ; Mask inventory bitfield (mask MASKID = bit MASKID)
```

**Order of includes in Oracle_main.asm:**
1. Graphics (for dw references)
2. Menu (for UI code)
3. Effects (for gameplay code)
4. Equipment (for hooks)"""
    },
    {
        "instruction": "What's the difference between Oracle_*, OOS_*, and ZSO_* namespace prefixes?",
        "thinking": "Namespace conventions are critical for Oracle codebase organization. Need to explain each prefix and when to use them.",
        "output": """**Oracle_* - Main Oracle Namespace**
```asm
namespace Oracle
{{
    CheckNightTime:  ; Becomes Oracle_CheckNightTime
        LDA $7EF3C7
        RTL
}}
```
**Use for:** Core Oracle of Secrets code (systems, items, menus, dungeons)

---

**OOS_* - Oracle of Seasons Legacy**
```asm
; No namespace - direct labels
OOS_LinkState:
    db $00

OOS_UpdateSeasons:
    RTL
```
**Use for:** Code ported from Oracle of Seasons prototype (rare, mostly replaced)

---

**ZSO_* - ZScream Oracle Integration**
```asm
; ZScream code lives outside namespace
ZSO_LoadSprites:
    ; ZScream's sprite loading
    RTL

; Bridge into Oracle namespace
namespace Oracle
{{
    Oracle_ZSO_LoadSprites = ZSO_LoadSprites
}}
```
**Use for:** ZScream/ZSCustomOverworld integration points

---

**Why separate namespaces?**

1. **Oracle_* is namespaced** - Prevents label collisions, organizes code
2. **ZSO_* is not namespaced** - ZScream code expects global labels
3. **OOS_* is legacy** - Being phased out, don't use for new code

**Calling between namespaces:**
```asm
; From Oracle code, call ZScream
namespace Oracle
{{
    MyOracleCode:
        JSL Oracle_ZSO_LoadSprites  ; Use bridged name
        RTL
}}

; From ZScream code, call Oracle
ZSO_CustomHook:
    JSL Oracle_CheckNightTime  ; Direct call with prefix
    RTL
```

**File organization:**
- `Oracle/*.asm` - Oracle_* code
- `ZScream/*.asm` - ZSO_* code
- `Legacy/*.asm` - OOS_* code (deprecated)"""
    }
]


def generate_agahnim_samples(count: int = 350) -> List[Dict]:
    """Generate synthetic Agahnim (build) examples."""
    samples = []

    # Common substitutions for variety
    addresses = ["$00F000", "$00ABCD", "$00D7A2", "$008234", "$00C45F"]
    routine_names = ["MyCustomHook", "NewFeatureCode", "CustomHandler", "PatchRoutine", "ExtendedLogic"]
    namespaces = ["Oracle", "Items", "Sprites", "Dungeons", "Menus"]
    routine_pairs = [
        ("Oracle_LoadItem", "Oracle_CheckInventory"),
        ("Sprite_Initialize", "Sprite_CheckCollision"),
        ("Menu_DrawCursor", "Menu_HandleInput"),
        ("Dungeon_LoadRoom", "Dungeon_SpawnEnemies")
    ]
    mask_names = ["Bunny", "Stone", "Giant", "Skull", "Truth"]

    for template in AGAHNIM_TEMPLATES * (count // len(AGAHNIM_TEMPLATES) + 1):
        if len(samples) >= count:
            break

        # Substitute placeholders
        instruction = template["instruction"].format(
            address=random.choice(addresses),
            routine_name=random.choice(routine_names),
            namespace=random.choice(namespaces),
            routine_a=random.choice(routine_pairs)[0],
            routine_b=random.choice(routine_pairs)[1]
        )

        output = template["output"].format(
            address=random.choice(addresses),
            routine_name=random.choice(routine_names),
            namespace=random.choice(namespaces),
            routine_a=random.choice(routine_pairs)[0],
            routine_b=random.choice(routine_pairs)[1]
        )

        thinking = template.get("thinking", "")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS["agahnim_build"]},
            {"role": "user", "content": instruction}
        ]

        assistant_content = f"<thinking>\n{thinking}\n</thinking>\n\n{output}" if thinking else output
        messages.append({"role": "assistant", "content": assistant_content})

        samples.append({
            "messages": messages,
            "_meta": {
                "source": "synthetic_generation",
                "domain": "agahnim_build",
                "confidence": 1.0,
                "synthetic": True
            }
        })

    return samples[:count]


def generate_majora_samples(count: int = 250) -> List[Dict]:
    """Generate synthetic Majora (Oracle) examples."""
    samples = []

    mask_names = ["Deku", "Goron", "Zora", "Giant", "Fierce Deity", "Bunny", "Stone", "Truth"]
    system_names = ["Time System", "Mask System", "Ocarina System", "Ranch System", "Minecart System"]

    for template in MAJORA_TEMPLATES * (count // len(MAJORA_TEMPLATES) + 1):
        if len(samples) >= count:
            break

        # Get random mask name
        selected_mask = random.choice(mask_names)

        instruction = template["instruction"]
        output = template["output"]

        # Replace MASKNAME placeholders (no .format() needed)
        output = output.replace("MASKNAME", selected_mask.lower())
        output = output.replace("MASSKNAME", selected_mask)
        output = output.replace("MASKID", str(random.randint(3, 7)))

        thinking = template.get("thinking", "")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS["majora_oracle"]},
            {"role": "user", "content": instruction}
        ]

        assistant_content = f"<thinking>\n{thinking}\n</thinking>\n\n{output}" if thinking else output
        messages.append({"role": "assistant", "content": assistant_content})

        samples.append({
            "messages": messages,
            "_meta": {
                "source": "synthetic_generation",
                "domain": "majora_oracle",
                "confidence": 1.0,
                "synthetic": True
            }
        })

    return samples[:count]


def main():
    output_dir = Path.home() / "src/lab/afs/training_data/synthetic"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== Generating Synthetic Training Examples ===\n")

    # Generate Agahnim samples
    print("Generating Agahnim (build) samples...")
    agahnim_samples = generate_agahnim_samples(350)
    agahnim_file = output_dir / "agahnim_synthetic.jsonl"
    with open(agahnim_file, "w") as f:
        for sample in agahnim_samples:
            f.write(json.dumps(sample) + "\n")
    print(f"  ✓ {len(agahnim_samples)} samples -> {agahnim_file.name}")

    # Generate Majora samples
    print("Generating Majora (Oracle) samples...")
    majora_samples = generate_majora_samples(250)
    majora_file = output_dir / "majora_synthetic.jsonl"
    with open(majora_file, "w") as f:
        for sample in majora_samples:
            f.write(json.dumps(sample) + "\n")
    print(f"  ✓ {len(majora_samples)} samples -> {majora_file.name}")

    # Summary
    print("\n=== Summary ===")
    print(f"Total synthetic samples: {len(agahnim_samples) + len(majora_samples)}")
    print(f"  Agahnim (build): {len(agahnim_samples)}")
    print(f"  Majora (Oracle): {len(majora_samples)}")
    print(f"\nOutput directory: {output_dir}")

    # Combined stats with filtered data
    filtered_dir = Path.home() / "src/lab/afs/training_data/filtered"
    print("\n=== Combined Dataset Statistics ===")

    totals = {
        "agahnim_build": 166,
        "majora_oracle": 65,
        "farore_debug": 1562,
        "veran_hardware": 2394,
        "nayru_codegen": 2397
    }

    totals["agahnim_build"] += len(agahnim_samples)
    totals["majora_oracle"] += len(majora_samples)

    print(f"{'Domain':<20} {'Filtered':<10} {'Synthetic':<10} {'Total':<10}")
    print("-" * 50)
    print(f"{'Agahnim (build)':<20} {166:<10} {len(agahnim_samples):<10} {totals['agahnim_build']:<10}")
    print(f"{'Majora (Oracle)':<20} {65:<10} {len(majora_samples):<10} {totals['majora_oracle']:<10}")
    print(f"{'Farore (debug)':<20} {1562:<10} {0:<10} {1562:<10}")
    print(f"{'Veran (hardware)':<20} {2394:<10} {0:<10} {2394:<10}")
    print(f"{'Nayru (codegen)':<20} {2397:<10} {0:<10} {2397:<10}")
    print("-" * 50)
    print(f"{'TOTAL':<20} {6584:<10} {600:<10} {sum(totals.values()):<10}")


if __name__ == "__main__":
    main()
