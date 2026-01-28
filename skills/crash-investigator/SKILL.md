---
name: crash-investigator
description: Autonomous crash analysis for Mesen2. Captures execution traces upon crash/pause, resolves symbols using z3ed, and generates annotated reports for debugging.
---

# Crash Investigator

## Scope
- **Detection**: Monitors Mesen2 for pauses (breakpoints) or manual triggers.
- **Data Capture**: Retrieves CPU state (registers) and execution trace (PC history).
- **Analysis**: Resolves raw addresses to symbols and source lines using `z3ed`.
- **Reporting**: Generates Markdown reports ready for LLM consumption.

## Core Capabilities

### 1. Manual Dump
Trigger an immediate analysis of the current state.
- `dump`: "I just saw a crash, analyze it."

### 2. Monitoring (The Sentinel)
Run in background to catch intermittent crashes.
- `monitor`: Polls emulator state. If it pauses (hit breakpoint/crash), auto-dumps.

### 3. Trace Blame
Maps the execution history to source code.
- Uses `z3ed rom-resolve-address` to turn `$07B107` into `Link_ResetProperties (Link.asm:45)`.

## Workflow

1.  **Start Monitor**: `crash-investigator monitor`.
2.  **Repro Bug**: Play game until it crashes (CPU JAM / Breakpoint).
3.  **Auto-Dump**: Tool detects pause, captures trace, resolves symbols.
4.  **Review**: Read `crash_reports/crash_20260125_120000.md`.
5.  **Reason**: Paste report into LLM: "Why did it crash at `Link_Update`?"

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/crash_dump.py`
- **Mesen2**: Must be running with socket server.
- **z3ed**: Must be built with symbol support.
- **Symbols**: ROM directory must contain `.mlb` or `.sym` files.

## Example Prompts
- "Monitor for crashes while I play the dungeon."
- "Dump the current state; the game is softlocked."
- "Analyze the last crash report."

## Troubleshooting
- **No Trace Data**: Ensure Mesen2 trace logging is enabled (internal buffer).
- **No Symbols**: Check if `.mlb` file exists next to ROM. Run `z3ed rom-resolve-address` to verify.
- **Connection Error**: Restart Mesen2.
