---
name: mesen2-oos-debugging
description: End-to-end Oracle of Secrets debugging using the Mesen2-OOS socket CLI, z3ed, and label/symbol tooling. Use for breakpoint/trace capture, memory inspection, savestate repro, overlays, or crash/regression triage (replaces mesen2-mcp and legacy Lua bridge workflows).
---

# Mesen2-OOS Debugging

## Overview
Drive Mesen2-OOS from the socket CLI to reproduce bugs, capture evidence, and map runtime behavior back to labels and source.

## Quick start
1. Work from the repo root: `~/src/hobby/oracle-of-secrets`.
2. Launch Mesen2-OOS with the target ROM (prefer isolated profiles via `scripts/mesen2_launch_instance.sh`).
3. Ensure a socket exists at `/tmp/mesen2-*.sock` or set `MESEN2_AUTO_ATTACH=1`.
4. Run:
   - `python3 scripts/mesen2_client.py health`
   - `python3 scripts/mesen2_client.py diagnostics`
   - `python3 scripts/mesen2_client.py debug-status`
   - `python3 scripts/mesen2_client.py capabilities`

## Debugging flow
1. **Stabilize**: Pause, capture `diagnostics`, and save a reproducible state (`capture --json`, `save`, `lib-save`).
2. **Label**: Sync vanilla labels (`labels-sync`) or load project symbols (`scripts/export_symbols.py --sync`). Use `labels-refresh --sync` when USDASM indexes are stale.
3. **Reproduce**: Use `repro`, `trace`, `breakpoint`, and `watch` to isolate the trigger.
4. **Inspect**: Use `cpu`, `pc`, `disasm`, `eval`, `mem-read`, and `mem-search` to inspect the failure.
5. **Annotate**: Use `state-diff`, `state-compare`, `draw-path`, `collision-overlay`, and `screenshot` to document.
6. **Verify**: Re-run `repro` or `lib-verify` after fixes.

## Key decisions
- Launch an isolated Mesen2 instance when another agent or human is using the default profile.
- Prefer watch profiles (`watch --profile overworld`) before manual watches.
- Treat `labels-sync` as vanilla-only; use `export_symbols.py --sync` for Oracle labels.

## Integration notes
- **yaze/z3dk**: All use the same `MESEN2_SOCKET_PATH` env var for socket targeting; set it when multiple Mesen2 instances exist so the CLI, yaze, and z3lsp target the same instance.
- **z3dk/z3ed**: Use `z3ed` for ROM validation and `scripts/export_symbols.py --sync` for Oracle labels; refresh z3dk indexes with `python3 scripts/mesen2_client.py labels-refresh` when symbols look stale.
- **ALTTP tooling**: Use Hyrule Historian for disassembly/RAM lookup; use book-of-mudora for ROM map checks and hook validation.
- **YAZE**: Call `sync <state_path>` after save/load when yaze needs updated state metadata.

## Knowledge References
Before debugging, consult these for context:
- Game architecture: `~/.context/knowledge/alttp/architecture.md`
- RAM addresses: `~/.context/knowledge/alttp/ram_map.md`
- Vanilla routines: `~/.context/knowledge/alttp/routine_index.md`
- Oracle flags/progression: `~/.context/knowledge/hobby/oracle-progression.md`
- Sprite tables: `~/.context/knowledge/hobby/oracle-sprite-ram.md`
- Debug workflows: `~/.context/knowledge/hobby/workflows.md`
- Disassembly bank map: `~/.context/knowledge/hobby/usdasm.md`
- SNES hardware: `~/.context/knowledge/snes/cpu_memory.md`

## References
- `references/cli-cheatsheet.md`
- `references/command-map.md`
- `references/troubleshooting.md`
- `references/triage-playbook.md`
