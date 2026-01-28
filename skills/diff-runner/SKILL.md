---
name: diff-runner
description: Regression testing tool for Oracle of Secrets. Records gameplay scenarios and replays them on new builds to detect logic bugs or desyncs.
---

# Diff Runner

## Scope
- **Regression Testing**: Verify that logic changes didn't break existing behavior.
- **State Comparison**: Compares critical game state (Link pos, Mode, Inventory) frame-by-frame (or action-by-action).

## Core Capabilities

### 1. Record
Execute a scenario script and capture the "Golden Trace".
- `record scenario.json trace.json`

### 2. Verify
Replay a trace on the current ROM and assert state matches.
- `verify trace.json`

## Workflow

1.  **Create Scenario**: Write a JSON list of inputs: `[{"input": "Right", "frames": 60}, ...]`.
2.  **Baseline**: Run `record` on the *stable* ROM build.
3.  **Dev**: Apply your changes/patches.
4.  **Test**: Run `verify` on the *new* ROM build.
5.  **Result**: "Pass" or "Divergence at Step 45".

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/diff_runner.py`.
- **Mesen2**: Running with socket server.

## Example Prompts
- "Record a baseline trace for the 'walk_to_dungeon' scenario."
- "Verify the current build against the 'boss_fight' trace."

## Troubleshooting
- **Desyncs**: Emulator RNG or uninitialized RAM can cause non-deterministic behavior. Ensure the scenario includes a hard reset or state load at the start.
