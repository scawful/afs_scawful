---
name: chaos-monkey
description: Automated fuzzer for Oracle of Secrets. Injects random inputs to stress-test the game engine and detect crashes or softlocks.
---

# Chaos Monkey (Fuzzer)

## Scope
- **Stress Testing**: Subject the game to high-intensity input streams.
- **Edge Case Discovery**: Find bugs caused by simultaneous inputs (e.g., L+R+Start) or frame-perfect transitions.
- **Integration**: Automatically triggers `crash-investigator` if the game breaks.

## Core Capabilities

### 1. Gameplay Fuzzing
- `mode: gameplay`
- Simulates a "frantic" player. Randomly moves, attacks, and uses items.
- Duration: Configurable (default 60s).

### 2. Glitch Hunting
- `mode: glitch`
- Injects 1-frame inputs and rapid pause/menu combos to break state logic.

## Workflow

1.  **Setup**: Use `navigator` to place Link in a target area (e.g., Boss Room).
2.  **Unleash**: `chaos-monkey run --mode glitch --duration 120`.
3.  **Monitor**: Watch for crashes. If Mesen2 pauses, a crash report is generated.

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/fuzzer.py`.
- **Mesen2**: Running with socket server.
- **Skill**: `crash-investigator` (for dumping).

## Example Prompts
- "Run the Chaos Monkey in the Dungeon Entrance for 2 minutes."
- "Stress test the menu system with glitch mode."

## Troubleshooting
- **Input Conflict**: Ensure no other agents (or humans) are controlling Mesen2.
- **False Positives**: "Glitch mode" might legitimately open/close the menu repeatedly. This is expected.
