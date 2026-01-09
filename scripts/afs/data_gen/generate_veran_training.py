#!/usr/bin/env python3
"""Generate training samples for Veran (hardware knowledge expert).

Addresses critical knowledge gaps identified in evaluation:
- DMA vs SPU confusion
- INIDISP/PPU register names
- ALTTP RAM addresses
- HDMA operation
"""

import json
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path.home() / ".context" / "training_pools"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_sample(input_text: str, output_text: str, tags: list[str]) -> dict:
    """Create a training sample in standard format."""
    return {
        "input": input_text,
        "output": output_text,
        "domain": "snes",
        "source": "manual_generation",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "expert": "veran",
            "tags": tags,
            "quality_score": 0.95,  # Manual samples are high quality
            "verified": True,
        }
    }


# Critical: DMA registers (fix SPU confusion)
DMA_SAMPLES = [
    create_sample(
        "What are SNES registers $4300-$4305?",
        "Registers $4300-$4305 are DMA (Direct Memory Access) channel 0 registers, NOT audio/SPU registers. They control high-speed data transfers between CPU memory and PPU/WRAM:\n\n- $4300 (DMAP0): DMA parameters (direction, mode, increment)\n- $4301 (BBAD0): B-bus target address (PPU register)\n- $4302-$4304: A-bus source address (CPU memory)\n- $4305-$4306: Transfer byte count (CRITICAL - must be set!)\n\nThe SNES has 8 DMA channels (0-7), each with its own register set at $43x0-$43xA.",
        ["dma", "hardware", "registers"],
    ),
    create_sample(
        "Is $4300 an audio register on the SNES?",
        "No! $4300 is NOT an audio register. It's the DMA Parameters register (DMAP0) for DMA channel 0.\n\nThe SNES audio registers are:\n- $2140-$2143: SPC700 communication ports\n- SPC700 internal registers (separate processor)\n\nDMA registers ($4300-$437F) handle fast memory transfers for graphics (VRAM, OAM, CGRAM), not audio. This is a common misconception.",
        ["dma", "spc700", "correction"],
    ),
    create_sample(
        "What enables a DMA transfer on the SNES?",
        "$420B (MDMAEN) enables DMA transfers. Each bit enables one DMA channel:\n- Bit 0: Channel 0\n- Bit 1: Channel 1\n- ... up to\n- Bit 7: Channel 7\n\nWriting a non-zero value to $420B immediately starts the transfer(s). The DMA channels must be configured first via $43x0-$43xA registers.\n\nFor HDMA (Horizontal DMA), use $420C (HDMAEN) instead.",
        ["dma", "registers", "enable"],
    ),
    create_sample(
        "How do I set up a DMA transfer to VRAM?",
        "Example: Transfer $1000 bytes from $7F8000 to VRAM $0000\n\n```asm\n; Set VRAM destination\nLDA #$80\nSTA $2115         ; VMAIN: increment after high byte\nSTZ $2116         ; VMADDL = 0\nSTZ $2117         ; VMADDH = 0\n\n; Configure DMA channel 0\nLDA #$01\nSTA $4300         ; Mode 1: two-register, increment\nLDA #$18\nSTA $4301         ; B-bus: $2118 (VMDATAL)\n\n; Source address\nLDA #$00\nSTA $4302         ; A1T0L\nLDA #$80\nSTA $4303         ; A1T0H\nLDA #$7F\nSTA $4304         ; A1B0 (bank)\n\n; Transfer length (CRITICAL!)\nSTZ $4305         ; DAS0L = 0\nLDA #$10\nSTA $4306         ; DAS0H = $10 ($1000 bytes)\n\n; Start transfer\nLDA #$01\nSTA $420B         ; Enable channel 0\n```",
        ["dma", "vram", "example"],
    ),
]

# Critical: PPU registers (INIDISP etc)
PPU_SAMPLES = [
    create_sample(
        "What is the SNES register $2100 used for?",
        "$2100 is INIDISP (Initial Display Settings), controlling screen brightness and forced blanking:\n\n- Bit 7: Forced Blanking (1=screen off, safe for VRAM access)\n- Bits 4-6: Unused\n- Bits 0-3: Brightness (0=black, 15=full brightness)\n\nCommon usage:\n```asm\n; Turn off screen for VRAM access\nLDA #$80\nSTA $2100\n\n; Full brightness, screen on\nLDA #$0F\nSTA $2100\n```",
        ["ppu", "inidisp", "display"],
    ),
    create_sample(
        "What PPU register controls screen brightness?",
        "$2100 (INIDISP) controls screen brightness. Bits 0-3 set brightness level (0=black, 15=full). Setting bit 7 enables forced blanking, turning off the display entirely.\n\nThis register is essential for:\n1. Fading effects (gradual brightness changes)\n2. Safe VRAM access during forced blank\n3. Turning off display during initialization",
        ["ppu", "inidisp", "brightness"],
    ),
    create_sample(
        "How do I enable forced blanking on the SNES?",
        "Set bit 7 of $2100 (INIDISP):\n\n```asm\n; Enable forced blank (screen off)\nLDA #$80\nSTA $2100\n\n; Now safe to write VRAM, OAM, CGRAM\n; ...\n\n; Restore display (full brightness)\nLDA #$0F\nSTA $2100\n```\n\nForced blanking is required for safe VRAM/OAM/CGRAM access outside of VBlank.",
        ["ppu", "blanking", "vram"],
    ),
]

# Critical: HDMA (completely unknown to Veran)
HDMA_SAMPLES = [
    create_sample(
        "What is HDMA on the SNES and how does it work?",
        "HDMA (Horizontal DMA) transfers data once per scanline during active display, enabling per-scanline effects like:\n- Color gradients (sky effects)\n- Window position changes (spotlight)\n- Scroll register changes (parallax/wavey effects)\n- Mode 7 parameter updates\n\nKey differences from regular DMA:\n1. Triggered once per H-blank (horizontal blanking period)\n2. Uses indirect table format in RAM\n3. Enabled via $420C (HDMAEN), not $420B\n4. Runs during visible display, not just VBlank\n\nHDMA uses the same channel registers ($43x0-$43xA) but with different table format.",
        ["hdma", "hardware", "scanline"],
    ),
    create_sample(
        "What register enables HDMA?",
        "$420C (HDMAEN) enables HDMA channels. Like $420B for DMA, each bit enables one channel (0-7).\n\nUnlike regular DMA which runs once when enabled, HDMA runs every scanline during active display until disabled or the table terminates.\n\nHDMA table format in RAM:\n- Byte 0: Scanline count (or $00 to terminate)\n- Bytes 1+: Data to transfer (or indirect pointer if indirect mode)",
        ["hdma", "enable", "registers"],
    ),
    create_sample(
        "How do I create a color gradient using HDMA?",
        "Example: Sky gradient using HDMA to $2132 (fixed color)\n\n```asm\n; HDMA table in RAM\nHDMATable:\n    .db $10, $00, $10, $1F  ; 16 lines: blue value $00, $10, $1F\n    .db $10, $00, $0F, $1F  ; 16 lines: slightly darker\n    .db $00                  ; End of table\n\n; Setup HDMA channel 7\nLDA #$02            ; Mode 2: write to p twice (for COLDATA)\nSTA $4370           ; DMAP7\nLDA #$32            ; B-bus: $2132 (COLDATA)\nSTA $4371\n\n; Table address\nLDA #<HDMATable\nSTA $4372\nLDA #>HDMATable\nSTA $4373\nLDA #^HDMATable\nSTA $4374\n\n; Enable HDMA channel 7\nLDA #$80\nSTA $420C\n```",
        ["hdma", "gradient", "example"],
    ),
]

# Critical: ALTTP RAM (wrong game name, wrong addresses)
ALTTP_SAMPLES = [
    create_sample(
        "What RAM address stores Link's X coordinate in A Link to the Past?",
        "Link's X coordinate in A Link to the Past is stored at $7E0022 (2 bytes, little-endian).\n\nRelated position addresses:\n- $7E0020: Link Y coordinate\n- $7E0022: Link X coordinate\n- $7E0024: Previous Y\n- $7E0026: Previous X\n- $7E002C: Direction (0=Up, 2=Down, 4=Left, 6=Right)\n\nNote: These are 16-bit pixel coordinates within the current area.",
        ["alttp", "ram", "position"],
    ),
    create_sample(
        "What is the correct RAM address for Link's position in Zelda 3?",
        "In The Legend of Zelda: A Link to the Past (Zelda 3):\n\n- $7E0022: Link's X coordinate (16-bit)\n- $7E0020: Link's Y coordinate (16-bit)\n\nNOTE: This is NOT $7E0014. That address is sometimes confused from other games or documentation errors. Always verify against the official disassembly.\n\nTo read Link's X in assembly:\n```asm\nLDA $0022  ; If DP=$7E00\n; or\nLDA $7E0022  ; Full 24-bit address\n```",
        ["alttp", "ram", "correction"],
    ),
    create_sample(
        "Where is Link's health stored in A Link to the Past?",
        "Link's health in ALTTP:\n- $7E0046: Current health (hearts * 8, so 24 HP = 3 hearts)\n- $7EF373: Maximum health\n\nEach heart is worth 8 units. Full hearts (typically 3 to start) = $18 in $7E0046.\n\nRelated addresses:\n- $7EF340: Sword level (0=none, 1=fighter, 2=master, 3=tempered, 4=golden)\n- $7EF341: Shield level\n- $7EF342: Armor/tunic (0=green, 1=blue, 2=red)",
        ["alttp", "ram", "health"],
    ),
    create_sample(
        "What game is A Link to the Past?",
        "A Link to the Past (ALTTP, also known as Zelda 3) is the third mainline Legend of Zelda game, released in 1991 for the Super Nintendo Entertainment System (SNES).\n\nIt is NOT:\n- Super Mario Bros. II (a completely different game series)\n- Zelda II: The Adventure of Link (NES game)\n- Link's Awakening (Game Boy game)\n\nALTTP introduced many series staples including the Master Sword, parallel worlds (Light/Dark World), and heart piece collection.",
        ["alttp", "game_info", "correction"],
    ),
]

# Mode 7 samples (Veran partially knows this)
MODE7_SAMPLES = [
    create_sample(
        "What registers control Mode 7 on the SNES?",
        "Mode 7 uses these PPU registers:\n\n- $211A (M7SEL): Mode 7 settings (repeat, flip)\n- $211B (M7A): Matrix parameter A (also used for multiplication)\n- $211C (M7B): Matrix parameter B (also multiplicand)\n- $211D (M7C): Matrix parameter C\n- $211E (M7D): Matrix parameter D\n- $211F (M7X): Center X coordinate\n- $2120 (M7Y): Center Y coordinate\n\nThe transformation matrix is:\n```\n[ A  B ] [x - X]   [X]\n[ C  D ] [y - Y] + [Y]\n```\n\nM7A/M7B can also be used for signed 16x8 multiplication (result in $2134-$2136).",
        ["mode7", "ppu", "matrix"],
    ),
]

def main():
    """Generate and save training samples."""
    all_samples = (
        DMA_SAMPLES +
        PPU_SAMPLES +
        HDMA_SAMPLES +
        ALTTP_SAMPLES +
        MODE7_SAMPLES
    )

    output_path = OUTPUT_DIR / "veran_critical_training.jsonl"

    with open(output_path, "w") as f:
        for sample in all_samples:
            f.write(json.dumps(sample) + "\n")

    print(f"Generated {len(all_samples)} training samples")
    print(f"Output: {output_path}")

    # Summary by category
    print("\nSamples by category:")
    print(f"  DMA registers: {len(DMA_SAMPLES)}")
    print(f"  PPU registers: {len(PPU_SAMPLES)}")
    print(f"  HDMA: {len(HDMA_SAMPLES)}")
    print(f"  ALTTP RAM: {len(ALTTP_SAMPLES)}")
    print(f"  Mode 7: {len(MODE7_SAMPLES)}")


if __name__ == "__main__":
    main()
