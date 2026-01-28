---
name: visual-verifier
description: Visual verification agent for ROM hacks. Compares emulator screenshots against "Golden Masters" to detect regressions, glitches, or UI errors.
---

# Visual Verifier

## Scope
- Capture and manage "Golden Master" screenshots of game scenes.
- Perform visual regression testing via image diffing.
- Detect visual glitches (garbage tiles, palette errors).
- Verify UI state (text boxes, menu rendering).

## Core Capabilities

### 1. Screenshot Capture
Save the current emulator frame as a reference.
- `capture title_screen`: Saves `assets/visual_masters/title_screen.png`.

### 2. Regression Testing
Compare the current frame against a saved master.
- `verify title_screen`: Reports similarity percentage (e.g., 99.5%).
- Thresholds: Customizable (default 95%).

### 3. Glitch Detection (Experimental)
Analyze the frame for common SNES glitches.
- Detection of "Garbage Tiles" (high-frequency noise).
- Detection of "Black Screens" or "CPU Jam" visual signatures.

## Workflow

1.  **Initialize**: `capture room_0x1B` (When you know the room is correct).
2.  **Modify Code**: Apply an ASM patch or change room data.
3.  **Verify**: `verify room_0x1B`.
4.  **Result**: "Similarity 85% - Red Area Detected (Check Door palette)."

## Dependencies
- **Mesen2**: Running with socket server.
- **Tool**: `~/src/hobby/yaze/scripts/ai/visual_verifier.py`.
- **Libs**: `opencv-python`, `Pillow`.

## Example Prompts
- "Capture a master screenshot of the current room."
- "Verify if the title screen still looks correct."
- "Does the current scene match the 'dungeon_entrance' reference?"
- "Check for any visual glitches on the screen."

## Troubleshooting
- **Connection Error**: Ensure Mesen2 is running.
- **Low Similarity**: Check if animations (flicker, water) are causing noise. Capture master during a stable frame.
- **Resize Mismatch**: Ensure emulator window hasn't been scaled or filtered unexpectedly.
