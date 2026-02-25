#!/usr/bin/env python3
"""
Veran Gold Standard Dataset - 2026 Code Analysis
Real code-based training pairs derived from maku_tree.asm and water_collision.asm.
"""

import json
from pathlib import Path

gold_samples = [
    {
        "instruction": "Analyze the state machine of the Maku Tree sprite in `maku_tree.asm`.",
        "analysis": "The Maku Tree sprite utilizes a 4-state jump table (`JumpTableLocal`). State 0 (Handler): Initial check to see if Link has met the tree before (via `MakuTreeQuest` flag). State 1 (MeetLink): First meeting logic. Triggers message 0x20, sets the initial `MapIcon`, and transitions to State 2. State 2 (SpawnHeartContainer): Awards the Heart Container item (ID 0x3E) via `Link_ReceiveItem`. State 3 (HasMetLink): The recurring interaction state. It uses a table-driven approach (`SelectReactionMessage`) to provide progressive hints based on crystal count."
    },
    {
        "instruction": "Explain the message selection logic in `MakuTreeReactionTable`.",
        "analysis": "The `MakuTreeReactionTable` is a threshold-based reaction table. It consists of 3-byte entries: 1 byte for the crystal count threshold and 2 bytes for the message ID (`db threshold : dw message_id`). The logic (`SelectReactionMessage`) walks the table in descending order. The first entry where `crystal_count >= threshold` is selected. For example, if Link has 4 crystals, it skips the 7 and 5 thresholds and matches the 3 threshold, returning message 0x01C6 (Mid-game sense of threat)."
    },
    {
        "instruction": "What is the purpose of the `REP #$20` and `SEP #$20` instructions before calling `SelectReactionMessage`?",
        "analysis": "In 65816 assembly, these instructions toggle the register widths. `REP #$20` sets the Accumulator (A) to 16-bit mode. This is used here to load the 16-bit address of the `MakuTreeReactionTable` into the Direct Page pointer `$00` in a single `LDA.w #label : STA $00` operation. `SEP #$20` then returns the Accumulator to 8-bit mode before setting the bank byte (`MakuTreeReactionTable>>16`) into `$02`, completing the 24-bit pointer required by the subroutine."
    },
    {
        "instruction": "Analyze the flag write `LDA.l $7EF3D6 : ORA.b #$02 : STA.l $7EF3D6` in the Maku Tree logic.",
        "analysis": "This operation performs a bitwise OR on the SRAM address $7EF3D6. Specifically, it sets Bit 1 (value 0x02), which corresponds to the 'Hall of Secrets' (OOSPROG bit 1) progression flag. This ensures that the Hall of Secrets is accessible once the player has reached or interacted with the Maku Tree, marking a key narrative milestone."
    },
    {
        "instruction": "Explain the ABI hardening applied to the water collision hooks in `water_collision.asm`.",
        "analysis": "The hardening uses `PHD` (Push Direct Page) and `LDA #$0000 : TCD` (Transfer to Direct Page) at the start of the routine, followed by `PLD` (Pull Direct Page) before the `RTS/RTL`. This isolates the routine's Direct Page state. By forcing DP to $0000, the routine ensures it accesses RAM in the expected vanilla bank while protecting the caller's DP state. This prevents 'blackout' bugs where transition callers expect DP to remain at $0000 upon return."
    }
]

def generate_gold_jsonl():
    output_path = Path("afs/training_data/veran_v1_gold.jsonl")
    with open(output_path, "w") as f:
        for sample in gold_samples:
            # Format for Veran training: [Instruct] -> [Analysis]
            f.write(json.dumps({
                "messages": [
                    {"role": "system", "content": "You are Veran, the Oracle of Secrets Analysis Expert. You specialize in reverse engineering ROM structures and explaining game logic with high technical accuracy."},
                    {"role": "user", "content": sample["instruction"]},
                    {"role": "assistant", "content": sample["analysis"]}
                ]
            }) + "\n")
    print(f"Success: Created {len(gold_samples)} Gold Standard samples at {output_path}")

if __name__ == "__main__":
    generate_gold_jsonl()