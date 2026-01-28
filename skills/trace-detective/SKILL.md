---
name: trace-detective
description: Trace analysis expert for Mesen2 debugging. Captures execution logs, filters for key state changes (subroutines, RAM writes), and summarizes failure chains for expert consultation.
---

# Trace Detective

## Scope
- Capture execution traces from Mesen2 via `z3ed debug trace`.
- Analyze traces to identify crash vectors (infinite loops, invalid jumps, bad RAM writes).
- Summarize low-level logs into high-level behavioral narratives.
- Package context for expert debugging (handoffs to Qwen/Claude).

## Core Capabilities

### 1. Trace Capture
Use `z3ed` to pull the last N instructions or run forward with logging.
- `z3ed debug trace --count 5000` (Capture recent history).
- `z3ed debug trace --start --condition "pc==0x8000"` (Conditional trace).

### 2. Signal Filtering
Raw traces are noisy (`LDA`, `STA`, `ADC`...). Filter for:
- **Control Flow:** `JSL`, `JML`, `RTS`, `RTL` (Subroutine boundaries).
- **Key RAM:** Writes to `$7E0010` (GameMode), `$7E00A0` (RoomID), `$7EF3CC` (Follower).
- **Registers:** Sudden changes in `P` (status register) indicating 8/16-bit mode desyncs.

### 3. Narrative Generation
Translate opcode streams into "What happened":
> "At frame 102, routine `LinkState_07` was entered. It branched to `DoorCheck` but read a `0x00` from `$7EF3CC` (Follower), leading to an infinite loop at `$02804C`."

### 4. Expert Handoff
Prepare a "Debug Context Pack" for Qwen/Claude:
- **Trace Summary:** The narrative above.
- **Relevant ASM:** The source code for the routines identified in the trace.
- **Memory Snapshot:** Values of key variables at the time of crash.

## Workflow

1.  **Trigger:** User says "The game crashed when I entered the door."
2.  **Capture:** `trace-detective capture --frames 60` (while reproducing).
3.  **Analyze:** `trace-detective analyze --focus 7E0010` (Look for mode switches).
4.  **Report:** Generate markdown summary or prompt for the expert.

## Commands

- `trace-detective capture [--frames N]`: Dump recent execution log.
- `trace-detective analyze <logfile> [--focus ADDR]`: Filter and summarize.
- `trace-detective blame <addr>`: Find the instruction that last wrote to ADDR.

## Integration Dependencies
- `z3ed`: Must be in PATH (from `~/src/hobby/yaze/build/bin/Debug/z3ed`).
- `Mesen2`: Must be running with socket server active.

## Example Prompts
- "Capture the last 60 frames of execution trace."
- "Analyze the trace for any writes to GameMode ($7E0010)."
- "Why did the game crash when I entered the dungeon?"
- "Who wrote 0x00 to address $7EF3CC?"

## Troubleshooting
- **Connection Failed**: Ensure `z3ed` can connect to Mesen2 socket. Check `z3ed debug state`.
- **Empty Trace**: Verify `z3ed` was built with debug features. Ensure emulation is running during capture.
- **Noise**: Traces are verbose. Use `--focus` or filtering to narrow down relevant instructions.

