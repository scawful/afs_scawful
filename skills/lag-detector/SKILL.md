---
name: lag-detector
description: Performance profiler for Oracle of Secrets. Samples the CPU Program Counter (PC) to identify code hotspots and laggy routines using statistical analysis.
---

# Lag Detector

## Scope
- **Profiling**: Statistical sampling of CPU execution.
- **Hotspot Analysis**: Identify which routines consume the most cycles.
- **Source Mapping**: Map hotspots back to ASM files.

## Core Capabilities

### 1. Profile execution
- `run --duration 10`: Sample CPU for 10 seconds.
- Output: A heatmap of the most executed routines.

### 2. Identify Bottlenecks
- "Routine `Update_Sprites` executed 5000 times (40% of samples)."
- Helps pinpoint inefficient loops or heavy logic.

## Workflow

1.  **Setup**: Navigate to a laggy area (e.g., room with many enemies).
2.  **Profile**: `lag-detector run --duration 5`.
3.  **Analyze**: "Top hotspot is `Sprite_Draw` in `Sprites.asm`."

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/profiler.py`.
- **Mesen2**: Running with socket server.
- **z3ed**: For symbol resolution.

## Example Prompts
- "Profile the game for 10 seconds to find lag sources."
- "What routine is taking up the most CPU time right now?"

## Troubleshooting
- **No Hotspots**: Ensure the game is not paused.
- **Unknown Symbols**: Ensure the ROM has a valid `.mlb` or `sourcemap.json`.
