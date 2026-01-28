---
name: memory-cartographer
description: Dynamic RAM analyzer for SNES debugging. Monitors memory ranges in real-time via Mesen2 to identify unknown variables, detect changes, and map memory usage.
---

# Memory Cartographer

## Scope
- Monitor SNES WRAM (`$7E0000-$7FFFFF`) in real-time.
- Detect changes in specific ranges during gameplay actions.
- Filter noise (counters, timers) to find significant state variables.
- Label unknown addresses and update memory maps.

## Core Capabilities

### 1. Dynamic Scanning
Watch a memory range while the user performs an action.
- `scan start 0x7E0000 0x7E2000`
- `scan stop` -> Reports all addresses that changed.

### 2. Intelligent Filtering
Filter the scan results to isolate specific behaviors.
- `filter increased`: Keep addresses that increased in value.
- `filter stable`: Keep addresses that stayed constant *during* the action but changed *from* start.
- `filter value 0x05`: Keep addresses that equal 0x05.

### 3. Change Detection (Noise Reduction)
Identify "noisy" addresses (frame counters, RNG) vs "state" addresses.
- Heuristic: If it changes every frame, it's a timer/counter.
- Heuristic: If it changes only on input, it's likely state.

### 4. Labeling & Mapping
- `label 0x7E04C0 "CaneBlockTimer"`
- `export`: Generates a markdown memory map or symbol file.

## Workflow

1.  **Hypothesis:** "Where is the timer for the Cane of Somaria block?"
2.  **Setup:** `scan start 0x7E0000 0x7E1000`.
3.  **Action:** In game, spawn a block. Wait 2 seconds.
4.  **Refine:** `scan stop`. `filter changed`.
5.  **Isolate:** "There are 50 candidates." -> `scan start`. Wait (do nothing). `scan stop`. `filter stable` (remove counters).
6.  **Verify:** `poke 0x7E04C0 0x01` (Set timer to 1). Block explodes? Found it.

## Dependencies
- **Mesen2**: Must be running with socket server.
- **Client**: `~/src/hobby/yaze/scripts/ai/memory_cartographer.py`.

## Example Prompts
- "I want to find the memory address for the player's health."
- "Scan range 0x7E0000 to 0x7E0100 for changes when I press A."
- "Filter the last scan for values that increased."
- "What addresses remained stable during the last action?"

## Troubleshooting
- **Connection Failed**: Ensure Mesen2 is running and the socket server is active (`/tmp/mesen2-*.sock`).
- **Slow Scanning**: Scanning large ranges (>0x400 bytes) is slow byte-by-byte. Reduce range or use `batch_execute` if available.
- **No Changes Detected**: Verify the range covers the expected variable location. Check `references/oracle_memory_map.md` for hints.

