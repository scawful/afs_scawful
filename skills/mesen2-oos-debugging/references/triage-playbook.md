# Debugging Triage Playbook

## Crash or black screen
1. `diagnostics` and `capture --json` to record baseline.
2. `save <slot>` or `lib-save "<label>"` for reproducibility.
3. `trace --action start --clear --labels true` then `run --frames 120` then `trace --action stop`.
4. `trace --count 200` or `trace-run --frames 120 --count 2000 --output trace.jsonl`.
5. Use `cpu`, `pc`, and `disasm` around the failure PC.

## Memory corruption
1. Identify the target WRAM address or range.
2. `mem-watch add <addr> --size N --depth 200`.
3. Reproduce the issue.
4. `mem-blame --addr <addr>` to list writers and timestamps.
5. `disasm <pc>` or `symbols <addr>` to map writers to labels.
6. Optional: `mem-snapshot before` then `mem-diff before` to spot divergent bytes.

## Regression or state mismatch
1. Capture two states (`save` or `lib-save`).
2. `state-compare --slot-a N --slot-b N` for structured diffs.
3. `state-diff` while reproducing to see live deltas.
4. Apply a `watch --profile <name>` for canonical variable snapshots.

## Movement or collision bugs
1. `draw-path "x1,y1,x2,y2" --color #00FF00 --frames 120` to annotate expected path.
2. `collision-overlay --enable` and `collision-dump --colmap A` for tile data.
3. `mem-read` for position/velocity variables in the watch profile.

## Symbols and labels
1. Refresh indexes: `labels-refresh [--sync] [--clear]` (pulls z3dk + USDASM updates).
2. Vanilla labels: `labels-sync [--clear]`.
3. Oracle labels: `python3 scripts/export_symbols.py --sync`.
4. Use `labels set|get|lookup` for quick ad-hoc tags while debugging.
5. Validate with `symbols Link_Main` and `disasm Link_Main`.

## Isolation
Use a dedicated instance when the default profile is in use:
`./scripts/mesen2_launch_instance.sh --instance <name> --owner <name> --title <name> --state-set oos168x_current`
