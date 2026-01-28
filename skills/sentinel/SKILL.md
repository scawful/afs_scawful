---
name: sentinel
description: Background watchdog for Oracle of Secrets. Monitors Mesen2 for crashes (pauses) and softlocks (stuck state/input), automatically triggering a crash dump investigation when detected.
---

# The Sentinel

## Scope
- **Crash Detection**: Detects when Mesen2 pauses (Breakpoint/CPU JAM).
- **Softlock Detection**: Detects "Stuck in Transition" or "Input Stagnation".
- **Action**: Triggers `crash-investigator` to dump trace and state.

## Core Capabilities

### 1. Active Monitoring
Run continuously alongside the game/agent.
- `python3 scripts/ai/sentinel.py`

### 2. Detection Logic
- **Crash**: Emulator `paused` state = True.
- **State Trap**: Game Mode (`$7E0010`) is playable (OW/Dungeon), but Submode is not `0x00` (Control) for > 5 seconds.
- **Stagnation**: Link (`$7E0020/22`) hasn't moved for > 10 seconds while in Control mode.

## Workflow

1.  **Launch**: `sentinel`.
2.  **Play/Test**: Run an agent test or manual play session.
3.  **Detect**: "Softlock Detected: Stuck in Transition".
4.  **Dump**: Sentinel invokes `crash_dump.py` -> `crash_reports/softlock_....md`.

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/sentinel.py`.
- **Mesen2**: Running with socket server.
- **Skill**: `crash-investigator` (for dumping logic).

## Example Prompts
- "Start the Sentinel to watch for softlocks."
- "I'm running a long pathfinding test, ensure the Sentinel is active."

## Troubleshooting
- **False Positives**: If you are standing still on purpose, Sentinel might complain. Kill it or ignore the report.
- **Connection**: Needs `mesen2-mcp` socket.
